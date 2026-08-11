"""
security_analysis.py
====================
Security Analysis for Sequential Dual-Bucket (SDB) Traffic Policing Middleware
Author: Boseth Rathnayake | LNBTI
Purpose: Simulate attack vectors, edge cases, and security vulnerabilities
         against the SDB middleware architecture.
"""

import json
import time
import math
import random
import hashlib
import string
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Tuple
from collections import defaultdict

# ──────────────────────────────────────────────────────────────────────────────
# SIMULATION MODELS (Pure Python — No Redis / Node required)
# ──────────────────────────────────────────────────────────────────────────────

class SimulatedTokenBucket:
    """Pure-Python token bucket for security simulation."""
    def __init__(self, capacity: float, fill_rate: float):
        self.capacity   = capacity
        self.fill_rate  = fill_rate
        self.tokens     = capacity
        self.last_refill = time.monotonic()

    def _refill(self, now: float):
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)
        self.last_refill = now

    def try_consume(self, amount: float = 1.0, now: float = None) -> bool:
        now = now or time.monotonic()
        self._refill(now)
        if self.tokens >= amount:
            self.tokens -= amount
            return True
        return False

    def inject_tokens(self, amount: float):
        """Simulates a token injection bypass attempt."""
        self.tokens = min(self.capacity, self.tokens + amount)


class SimulatedQueue:
    """Pure-Python FIFO queue simulating Redis list."""
    def __init__(self, max_size: int = 10):
        self.max_size = max_size
        self._queue: List[Dict] = []

    def enqueue(self, item: Dict) -> bool:
        if len(self._queue) >= self.max_size:
            return False  # Queue full — drop
        self._queue.append(item)
        return True

    def dequeue(self) -> Dict | None:
        return self._queue.pop(0) if self._queue else None

    def __len__(self):
        return len(self._queue)


class SimulatedCircuitBreaker:
    """Pure-Python circuit breaker."""
    def __init__(self, failure_threshold=3, reset_timeout=15.0, success_threshold=2):
        self.failure_threshold = failure_threshold
        self.reset_timeout     = reset_timeout
        self.success_threshold = success_threshold
        self.state             = 'CLOSED'
        self.failures          = 0
        self.successes         = 0
        self.last_failure_time = 0.0

    def fire(self, succeed: bool, now: float = None) -> Tuple[str, str]:
        now = now or time.monotonic()
        if self.state == 'OPEN':
            if now - self.last_failure_time > self.reset_timeout:
                self.state = 'HALF_OPEN'
                self.successes = 0
            else:
                return 'REJECTED', 'OPEN'

        if succeed:
            if self.state in ('CLOSED', 'HALF_OPEN'):
                self.successes += 1
                self.failures   = 0
                if self.state == 'HALF_OPEN' and self.successes >= self.success_threshold:
                    self.state    = 'CLOSED'
                    self.successes = 0
            return 'SUCCESS', self.state
        else:
            self.failures          += 1
            self.last_failure_time  = now
            if self.failures >= self.failure_threshold or self.state == 'HALF_OPEN':
                self.state    = 'OPEN'
                self.failures = 0
            return 'FAILURE', self.state


# ──────────────────────────────────────────────────────────────────────────────
# ATTACK VECTOR TESTS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class SecurityFinding:
    test_name: str
    category: str
    severity: str          # CRITICAL | HIGH | MEDIUM | LOW | INFO
    status: str            # VULNERABLE | MITIGATED | PARTIAL
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    recommendation: str = ""


findings: List[SecurityFinding] = []


# ── 1. BRUTE-FORCE LOGIN STORM ─────────────────────────────────────────────
def test_brute_force_storm():
    """
    Simulate 500 rapid sequential login attempts from a single IP.
    Expected: Rate limiter should throttle after capacity is exhausted.
    """
    capacity   = 10
    fill_rate  = 1     # 1 token/sec
    bucket     = SimulatedTokenBucket(capacity, fill_rate)
    queue      = SimulatedQueue(max_size=10)

    allowed = 0
    queued  = 0
    dropped = 0
    t0      = 0.0      # frozen time — no real wait

    for i in range(500):
        now = t0 + (i * 0.001)  # 1ms between requests — extremely fast
        if bucket.try_consume(now=now):
            allowed += 1
        else:
            if not queue.enqueue({"req_id": i, "username": f"user{i % 10}", "password": "pass"}):
                dropped += 1
            else:
                queued += 1

    bypass_ratio = allowed / 500
    status = "MITIGATED" if bypass_ratio <= (capacity / 500) * 1.2 else "VULNERABLE"

    findings.append(SecurityFinding(
        test_name    = "Brute-Force Login Storm (Single IP)",
        category     = "Availability / Authentication",
        severity     = "CRITICAL",
        status       = status,
        description  = "500 rapid login requests from a single source within 500ms.",
        details      = {
            "total_requests": 500,
            "allowed":        allowed,
            "queued":         queued,
            "dropped":        dropped,
            "bypass_ratio_%": round(bypass_ratio * 100, 2),
            "capacity":       capacity,
            "effective_throttle_%": round((500 - allowed) / 500 * 100, 2),
        },
        recommendation = (
            "Current token bucket effectively limits burst access. "
            "Consider adding per-IP rate limiting alongside the global bucket for stricter isolation."
        )
    ))


# ── 2. SLOW-DRIP CREDENTIAL STUFFING ──────────────────────────────────────
def test_slow_drip_attack():
    """
    Attacker sends exactly fill_rate - 1 requests per second to stay under radar.
    Checks if the rate limiter can detect sustained low-rate credential stuffing.
    """
    capacity  = 10
    fill_rate = 5      # 5 tokens/sec
    bucket    = SimulatedTokenBucket(capacity, fill_rate)

    attack_rps   = fill_rate - 1  # Stay just under fill rate
    duration_sec = 60
    total_sent   = attack_rps * duration_sec
    allowed_count = 0

    for sec in range(duration_sec):
        for _ in range(attack_rps):
            t = float(sec) + random.uniform(0, 1) / attack_rps
            if bucket.try_consume(now=t):
                allowed_count += 1

    # If almost all go through — no detection layer exists
    pass_rate = allowed_count / total_sent
    status    = "VULNERABLE" if pass_rate > 0.90 else "MITIGATED"

    findings.append(SecurityFinding(
        test_name    = "Slow-Drip Credential Stuffing",
        category     = "Authentication",
        severity     = "HIGH",
        status       = status,
        description  = (
            f"Attacker sends {attack_rps} req/sec (just below fill rate of {fill_rate}/sec) "
            f"over {duration_sec} seconds to evade the token bucket."
        ),
        details      = {
            "attack_rps":       attack_rps,
            "duration_sec":     duration_sec,
            "total_sent":       total_sent,
            "allowed":          allowed_count,
            "pass_rate_%":      round(pass_rate * 100, 2),
        },
        recommendation = (
            "The token bucket alone cannot detect slow-drip attacks since each request "
            "individually respects the rate limit. Implement a sliding-window anomaly detector "
            "or account-level lockout (e.g., ≥5 failures → lock 15 min) to complement the SDB mechanism."
        )
    ))


# ── 3. REDIS KEY MANIPULATION / INJECTION ─────────────────────────────────
def test_redis_key_injection():
    """
    Simulate adversarial Redis key inputs:
    - Newline injection in bucket key
    - Null-byte injection
    - Extremely long key (DoS on Redis memory)
    - Unicode surrogate injection
    """
    test_cases = [
        ("newline_injection",    "login_rate_limit\r\nSET evil_key 1"),
        ("null_byte_injection",  "login_rate_limit\x00malicious"),
        ("long_key_dos",         "A" * 65536),
        ("unicode_surrogate",    "login_rate_\ud800limit"),
        ("format_string",        "login_%s_%d_limit"),
        ("path_traversal",       "../../etc/passwd"),
    ]

    results = {}
    for name, key in test_cases:
        # Check if the key would be sanitized by a safe implementation
        safe = (
            "\r" not in key and
            "\n" not in key and
            "\x00" not in key and
            len(key) <= 512 and
            key.isprintable()
        )
        try:
            _ = key.encode('utf-8')
            encodable = True
        except (UnicodeEncodeError, UnicodeDecodeError):
            encodable = False

        results[name] = {
            "input_key_length": len(key),
            "passes_sanitization": safe,
            "utf8_encodable": encodable,
            "risk": "HIGH" if not safe else "LOW",
        }

    vulnerable_count = sum(1 for v in results.values() if not v["passes_sanitization"])
    status = "VULNERABLE" if vulnerable_count > 0 else "MITIGATED"

    findings.append(SecurityFinding(
        test_name    = "Redis Key Injection / Manipulation",
        category     = "Injection",
        severity     = "HIGH",
        status       = status,
        description  = "Tests adversarial inputs that could corrupt Redis key namespace or cause memory DoS.",
        details      = {
            "test_cases_run":     len(test_cases),
            "vulnerable_inputs":  vulnerable_count,
            "results":            results,
        },
        recommendation = (
            "Validate and sanitize all Redis key inputs. Enforce strict alphanumeric + underscore "
            "naming conventions for bucket keys. Use a key prefix schema (e.g., 'sdb:rl:{clientId}') "
            "validated against a regex before any Redis operation."
        )
    ))


# ── 4. REQUEST PAYLOAD SECURITY ───────────────────────────────────────────
def test_payload_security():
    """
    Test oversized payloads, prototype pollution, and JSON injection
    that could be queued into Redis and later executed.
    """
    test_payloads = {
        "normal":              {"username": "alice", "password": "secret123"},
        "oversized_payload":   {"username": "a" * 10000, "password": "b" * 10000},
        "prototype_pollution": {"__proto__": {"admin": True}, "username": "hack"},
        "json_injection":      {"username": '{"$where": "1==1"}', "password": "x"},
        "script_injection":    {"username": "<script>alert(1)</script>", "password": "x"},
        "sql_injection":       {"username": "admin'--", "password": "' OR '1'='1"},
        "null_byte":           {"username": "user\x00admin", "password": "pass"},
        "unicode_overflow":    {"username": "\uFFFD" * 1000, "password": "pass"},
    }

    results = {}
    queue   = SimulatedQueue(max_size=10)

    for name, payload in test_payloads.items():
        serialized = json.dumps(payload, ensure_ascii=False)
        size_kb    = len(serialized.encode('utf-8')) / 1024

        # Check basic sanitization guards
        username = str(payload.get("username", ""))
        issues   = []

        if len(serialized) > 4096:       issues.append("oversized_payload")
        if "__proto__" in serialized:    issues.append("prototype_pollution")
        if "<script" in username.lower(): issues.append("xss_in_username")
        if any(c in username for c in ["'", "--", ";"]):  issues.append("sql_chars")
        if "\x00" in username:           issues.append("null_byte")

        was_queued = queue.enqueue({"name": name, "payload": payload})

        results[name] = {
            "payload_size_kb": round(size_kb, 2),
            "issues_detected":  issues,
            "would_be_queued":  was_queued,
            "risk":             "HIGH" if issues else "LOW",
        }

    risky = [k for k, v in results.items() if v["issues_detected"]]
    status = "PARTIAL" if risky else "MITIGATED"

    findings.append(SecurityFinding(
        test_name    = "Request Payload Security (Queue Poisoning)",
        category     = "Injection / Input Validation",
        severity     = "HIGH",
        status       = status,
        description  = "Checks whether malicious request bodies can be stored in the Redis queue without sanitization.",
        details      = {
            "payloads_tested": len(test_payloads),
            "risky_payloads":  risky,
            "results":         results,
        },
        recommendation = (
            "Add a middleware layer to validate JSON schema before enqueueing. "
            "Enforce max body size (e.g., 4KB). Strip/reject null bytes and prototype keys. "
            "Sanitize username/password fields against known injection patterns."
        )
    ))


# ── 5. TOKEN BUCKET ARITHMETIC EDGE CASES ─────────────────────────────────
def test_token_arithmetic_edge_cases():
    """
    Probe the Lua token bucket script for arithmetic edge cases:
    - Negative time drift (clock skew between nodes)
    - Fractional fill rate accumulation errors
    - Token overshoot beyond capacity
    - Zero-capacity bucket
    - Integer overflow simulation
    """
    results = {}

    # 5a. Clock skew (time goes backwards)
    bucket = SimulatedTokenBucket(10, 1)
    bucket.tokens = 5
    bucket.last_refill = 100.0
    # Simulate clock skew: now < last_refill
    elapsed = -5.0   # negative time
    tokens_added = max(0, math.floor(elapsed * bucket.fill_rate))  # Safe: floor with guard
    expected_safe = 5 + tokens_added  # Should stay at 5
    results["clock_skew_negative_time"] = {
        "initial_tokens": 5,
        "time_elapsed":   elapsed,
        "tokens_added":   tokens_added,
        "final_tokens":   expected_safe,
        "safe":           expected_safe >= 0,
        "risk":           "MEDIUM" if expected_safe < 0 else "LOW",
    }

    # 5b. Fractional accumulation (1.5 tokens/sec, checked at 0.5s intervals)
    bucket2  = SimulatedTokenBucket(10, 1.5)
    consumed = 0
    t        = 0.0
    for _ in range(20):
        t += 0.5
        if bucket2.try_consume(now=t):
            consumed += 1
    theoretical_max = min(10, math.floor(0.5 * 1.5 * 20))  # Fill over 10s
    results["fractional_fill_rate"] = {
        "fill_rate":       1.5,
        "interval_sec":    0.5,
        "iterations":      20,
        "total_consumed":  consumed,
        "theoretical_max": theoretical_max,
        "overshoot":       consumed > theoretical_max,
        "risk":            "LOW",
    }

    # 5c. Token capacity overshoot
    bucket3 = SimulatedTokenBucket(10, 100)  # Very high fill rate
    bucket3.tokens = 9
    bucket3.last_refill = 0.0
    bucket3.try_consume(now=1.0)  # Should add 100 tokens but cap at 10
    results["capacity_overshoot"] = {
        "capacity":      10,
        "fill_rate":     100,
        "elapsed_sec":   1.0,
        "would_add":     100,
        "capped_at":     10,
        "actual_tokens": round(bucket3.tokens, 2),
        "safe":          bucket3.tokens <= 10,
        "risk":          "LOW" if bucket3.tokens <= 10 else "CRITICAL",
    }

    # 5d. Zero capacity bucket
    bucket4 = SimulatedTokenBucket(0, 0)
    result4 = bucket4.try_consume()
    results["zero_capacity"] = {
        "capacity":   0,
        "fill_rate":  0,
        "consumed":   result4,
        "expected":   False,
        "safe":       result4 == False,
        "risk":       "CRITICAL" if result4 else "LOW",
    }

    # 5e. Concurrent race window simulation
    concurrent_bucket = SimulatedTokenBucket(1, 0)  # Exactly 1 token, no refill
    race_results = []
    # Simulate 10 "concurrent" requests reading tokens before any writes commit
    for _ in range(10):
        if concurrent_bucket.tokens >= 1:
            # Without atomic Lua script, all would see 1 token
            race_results.append("CONSUMED")
        concurrent_bucket.tokens -= 1 if concurrent_bucket.tokens >= 1 else 0

    race_vulnerable = race_results.count("CONSUMED") > 1
    results["concurrent_race_window"] = {
        "initial_tokens":      1,
        "concurrent_requests": 10,
        "race_consumptions":   race_results.count("CONSUMED"),
        "race_vulnerable":     race_vulnerable,
        "mitigated_by":        "Lua atomic eval (Redis EVAL) in production",
        "risk":                "INFO — mitigated in actual Redis implementation",
    }

    issues = [k for k, v in results.items() if v.get("risk") in ("CRITICAL", "HIGH", "MEDIUM")]
    status = "PARTIAL" if issues else "MITIGATED"

    findings.append(SecurityFinding(
        test_name    = "Token Bucket Arithmetic Edge Cases",
        category     = "Logic / Arithmetic",
        severity     = "MEDIUM",
        status       = status,
        description  = "Probes token bucket for arithmetic edge cases: clock skew, fractional fill, overshoot, zero-capacity, race conditions.",
        details      = results,
        recommendation = (
            "Production Lua script handles most of these via Redis atomicity. "
            "Add explicit guards: max(0, timePassed) to handle clock skew, "
            "add monotonic timestamp validation, and enforce capacity > 0 at construction time."
        )
    ))


# ── 6. CIRCUIT BREAKER MANIPULATION ───────────────────────────────────────
def test_circuit_breaker_manipulation():
    """
    Attacker deliberately triggers circuit breaker to cause DoS:
    1. Flood with requests guaranteed to fail → trip the breaker
    2. During OPEN state, all legitimate users are blocked
    """
    cb = SimulatedCircuitBreaker(failure_threshold=3, reset_timeout=15.0)

    # Phase 1: Attacker sends failing requests to trip the breaker
    attacker_requests = 5
    for i in range(attacker_requests):
        status, state = cb.fire(succeed=False, now=float(i))

    state_after_attack = cb.state

    # Phase 2: Legitimate users now blocked
    blocked_legitimate = 0
    for i in range(20):
        outcome, state = cb.fire(succeed=True, now=float(attacker_requests + i))
        if outcome == 'REJECTED':
            blocked_legitimate += 1

    findings.append(SecurityFinding(
        test_name    = "Circuit Breaker DoS via Deliberate Failures",
        category     = "Availability",
        severity     = "HIGH",
        status       = "VULNERABLE" if blocked_legitimate > 0 else "MITIGATED",
        description  = (
            "Attacker deliberately sends failing requests to trip the circuit breaker, "
            "causing legitimate users to be blocked during the OPEN window."
        ),
        details      = {
            "attacker_failing_requests": attacker_requests,
            "failure_threshold":         3,
            "state_after_attack":        state_after_attack,
            "legitimate_blocked":        blocked_legitimate,
            "reset_timeout_sec":         15.0,
            "exposure_window_sec":       15.0,
        },
        recommendation = (
            "Differentiate between client-side errors (4xx) and server-side errors (5xx) — "
            "only trip the circuit on 5xx responses. Add per-client failure tracking "
            "to prevent a single malicious client from affecting the global circuit state. "
            "Consider a half-open exponential backoff strategy."
        )
    ))


# ── 7. QUEUE OVERFLOW / MEMORY EXHAUSTION ─────────────────────────────────
def test_queue_overflow():
    """
    Test unbounded queue growth: if max_size is not enforced,
    an attacker can exhaust Redis memory by queueing millions of requests.
    """
    configs = [
        ("no_limit",      SimulatedQueue(max_size=999999), 50000),
        ("limited_10",    SimulatedQueue(max_size=10),     50000),
        ("limited_100",   SimulatedQueue(max_size=100),    50000),
        ("limited_1000",  SimulatedQueue(max_size=1000),   50000),
    ]

    results = {}
    for name, q, n_requests in configs:
        queued  = 0
        dropped = 0
        for i in range(n_requests):
            if q.enqueue({"req_id": i}):
                queued += 1
            else:
                dropped += 1

        payload_mb = (queued * 256) / (1024 * 1024)  # ~256 bytes per entry
        results[name] = {
            "attempted":    n_requests,
            "queued":       queued,
            "dropped":      dropped,
            "queue_depth":  len(q),
            "memory_est_mb": round(payload_mb, 3),
            "risk":         "CRITICAL" if queued == n_requests else "LOW",
        }

    unbounded_risk = results["no_limit"]["risk"] == "CRITICAL"
    findings.append(SecurityFinding(
        test_name    = "Queue Overflow / Redis Memory Exhaustion",
        category     = "Availability / Resource Exhaustion",
        severity     = "CRITICAL",
        status       = "PARTIAL",
        description  = "Tests whether unbounded queue depth allows an attacker to exhaust Redis memory.",
        details      = results,
        recommendation = (
            "Enforce REDIS_MAXMEMORY and eviction policy (allkeys-lru). "
            "Always set a max queue depth (e.g., 1000 entries). "
            "Monitor queue length via /status endpoint and emit alerts when queue_length > 80% of max."
        )
    ))


# ── 8. HEADER / IP SPOOFING ───────────────────────────────────────────────
def test_header_ip_spoofing():
    """
    Test whether per-IP rate limiting can be bypassed by spoofing X-Forwarded-For headers.
    """
    real_ip       = "192.168.1.100"
    spoofed_ips   = [f"10.0.0.{i}" for i in range(1, 101)]  # 100 different spoofed IPs
    trusted_proxy = False  # Simulate no proxy trust validation

    results = {
        "real_ip":            real_ip,
        "spoofed_ips_tested": len(spoofed_ips),
        "trusted_proxy_validated": trusted_proxy,
        "bypass_possible":    not trusted_proxy,
        "requests_that_bypass": len(spoofed_ips) if not trusted_proxy else 0,
    }

    findings.append(SecurityFinding(
        test_name    = "X-Forwarded-For Header Spoofing",
        category     = "Authentication / Access Control",
        severity     = "HIGH",
        status       = "VULNERABLE" if not trusted_proxy else "MITIGATED",
        description  = (
            "Attacker rotates X-Forwarded-For values to bypass per-IP rate limiting, "
            "appearing as 100 different IPs to the middleware."
        ),
        details      = results,
        recommendation = (
            "Never trust X-Forwarded-For from untrusted sources. "
            "Use req.socket.remoteAddress as the authoritative IP, or configure a trusted proxy list. "
            "In Express.js, set app.set('trust proxy', 1) only if behind a known load balancer."
        )
    ))


# ──────────────────────────────────────────────────────────────────────────────
# SUMMARY BUILDER
# ──────────────────────────────────────────────────────────────────────────────

def build_summary(findings: List[SecurityFinding]) -> Dict[str, Any]:
    severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
    severity_counts = defaultdict(int)
    status_counts   = defaultdict(int)

    for f in findings:
        severity_counts[f.severity] += 1
        status_counts[f.status]     += 1

    risk_score = (
        severity_counts["CRITICAL"] * 10 +
        severity_counts["HIGH"]     * 7  +
        severity_counts["MEDIUM"]   * 4  +
        severity_counts["LOW"]      * 1
    )

    return {
        "total_tests":      len(findings),
        "severity_counts":  dict(severity_counts),
        "status_counts":    dict(status_counts),
        "overall_risk_score": risk_score,
        "risk_rating":      (
            "CRITICAL" if risk_score >= 40
            else "HIGH"   if risk_score >= 25
            else "MEDIUM" if risk_score >= 10
            else "LOW"
        ),
        "vulnerabilities":  [f.test_name for f in findings if f.status == "VULNERABLE"],
        "partial":          [f.test_name for f in findings if f.status == "PARTIAL"],
        "mitigated":        [f.test_name for f in findings if f.status == "MITIGATED"],
    }


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def run_security_analysis() -> Dict[str, Any]:
    print("=" * 60)
    print("  SDB Security Analysis — Running Tests")
    print("=" * 60)

    tests = [
        ("Brute-Force Storm",              test_brute_force_storm),
        ("Slow-Drip Credential Stuffing",  test_slow_drip_attack),
        ("Redis Key Injection",            test_redis_key_injection),
        ("Payload Security",               test_payload_security),
        ("Token Arithmetic Edge Cases",    test_token_arithmetic_edge_cases),
        ("Circuit Breaker Manipulation",   test_circuit_breaker_manipulation),
        ("Queue Overflow",                 test_queue_overflow),
        ("Header/IP Spoofing",             test_header_ip_spoofing),
    ]

    for name, fn in tests:
        print(f"  ▶ {name} ...", end=" ", flush=True)
        fn()
        print("DONE")

    summary = build_summary(findings)
    output  = {
        "analysis_type": "Security Analysis",
        "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "summary":       summary,
        "findings":      [asdict(f) for f in findings],
    }

    print("\n  Summary:")
    print(f"    Tests Run:          {summary['total_tests']}")
    print(f"    Vulnerable:         {len(summary['vulnerabilities'])}")
    print(f"    Partial:            {len(summary['partial'])}")
    print(f"    Mitigated:          {len(summary['mitigated'])}")
    print(f"    Risk Score:         {summary['overall_risk_score']} ({summary['risk_rating']})")
    print("=" * 60)

    return output


if __name__ == "__main__":
    import os
    result = run_security_analysis()
    out_path = os.path.join(os.path.dirname(__file__), "security_findings.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Results saved → {out_path}")
