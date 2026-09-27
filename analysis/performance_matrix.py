"""
performance_matrix.py
=====================
Performance Matrix for Sequential Dual-Bucket (SDB) Traffic Policing Middleware
Author: Boseth Rathnayake | LNBTI
Purpose: N=30 CRN discrete-event simulation — drop rate, latency percentiles,
         throughput, and queue wait times for SDB vs Token-Only baseline.
"""

import json
import math
import random
import time
import statistics
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Tuple

# ──────────────────────────────────────────────────────────────────────────────
# EXPERIMENT PARAMETERS (matching the abstract)
# ──────────────────────────────────────────────────────────────────────────────

SEED_BASE          = 42         # CRN base seed
N_TRIALS           = 30         # Independent trials
SIM_DURATION_SEC   = 60.0       # Simulation window per trial
BACKGROUND_RPS     = 50         # Increased from 5 to 50 for stress testing
SPIKE_SIZE         = 100        # Increased from 15 to 100
SPIKE_INTERVAL_SEC = 3.0        # Spike every 3 seconds

# Token Bucket Parameters
TB_CAPACITY        = 10         # Tokens (matches test suite config)
TB_FILL_RATE       = 5.0        # Tokens per second

# SDB Queue Sizes to evaluate
CONFIGS = [
    {"label": "Old Baseline (Cap=10, Q=0)", "cap": 10, "fill": 5.0, "q": 0},
    {"label": "Old SDB (Cap=10, Q=10)", "cap": 10, "fill": 5.0, "q": 10},
    {"label": "New SDB (Cap=30, Q=75)", "cap": 30, "fill": 15.0, "q": 75},
    {"label": "New SDB (Cap=30, Q=150)", "cap": 30, "fill": 15.0, "q": 150},
    {"label": "New SDB (Cap=30, Q=300)", "cap": 30, "fill": 15.0, "q": 300}
]

# Simulated backend latency distribution (log-normal, ms)
LATENCY_MU         = 4.5        # ln(ms) → median ≈ 90ms
LATENCY_SIGMA      = 0.6


# ──────────────────────────────────────────────────────────────────────────────
# CORE SIMULATION MODELS
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class Request:
    req_id:       int
    arrive_time:  float
    req_type:     str    # 'background' or 'spike'


@dataclass
class RequestResult:
    req_id:       int
    req_type:     str
    arrive_time:  float
    outcome:      str    # 'served' | 'queued' | 'dropped'
    latency_ms:   float  # 0 if dropped/queued without service
    queue_wait_ms: float


class TokenBucketSim:
    def __init__(self, capacity: float, fill_rate: float):
        self.capacity    = capacity
        self.fill_rate   = fill_rate
        self.tokens      = float(capacity)
        self.last_refill = 0.0

    def try_consume(self, now: float) -> bool:
        elapsed     = max(0.0, now - self.last_refill)
        added       = min(self.capacity - self.tokens, elapsed * self.fill_rate)
        self.tokens += added
        self.last_refill = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class QueueSim:
    """FIFO queue with configurable max depth."""
    def __init__(self, max_size: int):
        self.max_size = max_size
        self._q: List[Tuple[float, Request]] = []   # (enqueue_time, request)

    def enqueue(self, req: Request, now: float) -> bool:
        if len(self._q) >= self.max_size:
            return False
        self._q.append((now, req))
        return True

    def dequeue(self) -> Tuple[float, Request] | None:
        return self._q.pop(0) if self._q else None

    def __len__(self):
        return len(self._q)


def sample_latency(rng: random.Random) -> float:
    """Log-normal backend latency in ms."""
    return math.exp(LATENCY_MU + LATENCY_SIGMA * rng.gauss(0, 1))


# ──────────────────────────────────────────────────────────────────────────────
# TRAFFIC GENERATOR
# ──────────────────────────────────────────────────────────────────────────────

def generate_traffic(rng: random.Random) -> List[Request]:
    """
    Generate arrival events for one simulation trial:
    - Background: Poisson process (λ = BACKGROUND_RPS)
    - Spikes: SPIKE_SIZE simultaneous arrivals every SPIKE_INTERVAL_SEC
    """
    requests = []
    req_id   = 0

    # Background traffic via Poisson inter-arrival times
    t = 0.0
    while t < SIM_DURATION_SEC:
        inter = rng.expovariate(BACKGROUND_RPS)
        t    += inter
        if t < SIM_DURATION_SEC:
            requests.append(Request(req_id, t, 'background'))
            req_id += 1

    # Spike traffic
    spike_t = SPIKE_INTERVAL_SEC
    while spike_t < SIM_DURATION_SEC:
        for _ in range(SPIKE_SIZE):
            requests.append(Request(req_id, spike_t, 'spike'))
            req_id += 1
        spike_t += SPIKE_INTERVAL_SEC

    # Sort by arrival time
    requests.sort(key=lambda r: r.arrive_time)
    return requests


# ──────────────────────────────────────────────────────────────────────────────
# SDB SIMULATION ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def simulate_trial(requests: List[Request], queue_size: int, rng: random.Random) -> Dict[str, Any]:
    """
    Run one trial of the SDB (or token-only) simulator.
    queue_size = 0 → Token-Only (no queue, immediate drop if no token).
    queue_size > 0 → SDB with leaky FIFO queue.
    """
    tb      = TokenBucketSim(TB_CAPACITY, TB_FILL_RATE)
    q       = QueueSim(queue_size) if queue_size > 0 else None

    results: List[RequestResult] = []

    served  = 0
    queued  = 0
    dropped = 0

    # Process each request in arrival order
    for req in requests:
        now = req.arrive_time

        # 1. Token bucket gate
        if tb.try_consume(now):
            lat = sample_latency(rng)
            results.append(RequestResult(
                req_id=req.req_id, req_type=req.req_type,
                arrive_time=req.arrive_time, outcome='served',
                latency_ms=lat, queue_wait_ms=0.0
            ))
            served += 1
        else:
            # 2. Try to queue (SDB mode only)
            if q is not None and q.enqueue(req, now):
                queued += 1
                # Process queued requests that have tokens available (drain at fill rate)
                # Each dequeue waits 1/fill_rate seconds
            else:
                # 3. Drop
                results.append(RequestResult(
                    req_id=req.req_id, req_type=req.req_type,
                    arrive_time=req.arrive_time, outcome='dropped',
                    latency_ms=0.0, queue_wait_ms=0.0
                ))
                dropped += 1

    # Drain the queue after all arrivals
    if q is not None:
        drain_time = SIM_DURATION_SEC
        while True:
            item = q.dequeue()
            if item is None:
                break
            enq_time, req = item
            wait_time = 1.0 / TB_FILL_RATE  # Wait for next token
            drain_time += wait_time

            if tb.try_consume(drain_time):
                lat      = sample_latency(rng)
                wait_ms  = (drain_time - enq_time) * 1000
                results.append(RequestResult(
                    req_id=req.req_id, req_type=req.req_type,
                    arrive_time=req.arrive_time, outcome='served_from_queue',
                    latency_ms=lat, queue_wait_ms=wait_ms
                ))
                served += 1
                queued -= 1
            else:
                # Still no token — re-add 1 wait period
                drain_time += 1.0 / TB_FILL_RATE
                q._q.insert(0, (enq_time, req))

    total = len(requests)
    served_results  = [r for r in results if r.outcome in ('served', 'served_from_queue')]
    latencies_ms    = [r.latency_ms for r in served_results]
    queue_waits_ms  = [r.queue_wait_ms for r in results if r.outcome == 'served_from_queue']

    def percentile(data: List[float], p: float) -> float:
        if not data: return 0.0
        data_s = sorted(data)
        k      = (len(data_s) - 1) * p / 100
        lo, hi = int(k), min(int(k) + 1, len(data_s) - 1)
        return data_s[lo] + (data_s[hi] - data_s[lo]) * (k - lo)

    drop_rate = dropped / total if total > 0 else 0.0
    throughput_rps = len(served_results) / SIM_DURATION_SEC

    return {
        "total_requests":  total,
        "served":          len([r for r in results if r.outcome == 'served']),
        "served_queued":   len([r for r in results if r.outcome == 'served_from_queue']),
        "queued_pending":  queued,
        "dropped":         dropped,
        "drop_rate":       round(drop_rate * 100, 4),
        "throughput_rps":  round(throughput_rps, 4),
        "latency_p50_ms":  round(percentile(latencies_ms, 50), 2),
        "latency_p95_ms":  round(percentile(latencies_ms, 95), 2),
        "latency_p99_ms":  round(percentile(latencies_ms, 99), 2),
        "latency_mean_ms": round(statistics.mean(latencies_ms) if latencies_ms else 0, 2),
        "latency_std_ms":  round(statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0, 2),
        "queue_wait_p50_ms": round(percentile(queue_waits_ms, 50), 2),
        "queue_wait_p95_ms": round(percentile(queue_waits_ms, 95), 2),
        "spike_drop_rate": round(
            sum(1 for r in results if r.outcome == 'dropped' and r.req_type == 'spike') /
            max(1, sum(1 for r in requests if r.req_type == 'spike')) * 100, 4
        ),
        "background_drop_rate": round(
            sum(1 for r in results if r.outcome == 'dropped' and r.req_type == 'background') /
            max(1, sum(1 for r in requests if r.req_type == 'background')) * 100, 4
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# STATISTICAL HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def mean_ci(data: List[float], z: float = 1.96) -> Tuple[float, float, float]:
    """Returns (mean, lower_95%_CI, upper_95%_CI)."""
    n  = len(data)
    mu = statistics.mean(data)
    se = statistics.stdev(data) / math.sqrt(n)
    return mu, mu - z * se, mu + z * se


def cohen_d(a: List[float], b: List[float]) -> float:
    """Effect size (Cohen's d) between two samples."""
    pooled_std = math.sqrt(
        ((len(a) - 1) * statistics.variance(a) + (len(b) - 1) * statistics.variance(b)) /
        (len(a) + len(b) - 2)
    )
    return (statistics.mean(a) - statistics.mean(b)) / pooled_std if pooled_std > 0 else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER
# ──────────────────────────────────────────────────────────────────────────────

def run_performance_matrix() -> Dict[str, Any]:
    print("=" * 60)
    print("  SDB Performance Matrix — N=30 CRN Simulation")
    print("=" * 60)

    all_configs: Dict[str, Dict[str, Any]] = {}

    for cfg in CONFIGS:
        label = cfg["label"]
        q_size = cfg["q"]
        global TB_CAPACITY, TB_FILL_RATE
        TB_CAPACITY = cfg["cap"]
        TB_FILL_RATE = cfg["fill"]
        print(f"\n  ▶ Config: {label} ...", flush=True)

        trial_results = []
        for trial in range(N_TRIALS):
            # CRN: same seed per trial across all configs
            rng      = random.Random(SEED_BASE + trial)
            traffic  = generate_traffic(rng)
            # Reset RNG to same state for latency sampling (CRN)
            rng_lat  = random.Random(SEED_BASE + trial + 1000)
            result   = simulate_trial(traffic, q_size, rng_lat)
            trial_results.append(result)
            print(f"    Trial {trial + 1:02d}/{N_TRIALS} — drop_rate={result['drop_rate']:.2f}%  "
                  f"p95_lat={result['latency_p95_ms']:.1f}ms  "
                  f"tput={result['throughput_rps']:.2f} rps")

        # Aggregate across trials
        def agg(key):
            vals = [r[key] for r in trial_results]
            mu, lo, hi = mean_ci(vals)
            return {
                "mean":   round(mu, 4),
                "std":    round(statistics.stdev(vals), 4),
                "min":    round(min(vals), 4),
                "max":    round(max(vals), 4),
                "ci95_lo": round(lo, 4),
                "ci95_hi": round(hi, 4),
                "raw":    [round(v, 4) for v in vals],
            }

        all_configs[label] = {
            "queue_size":          q_size,
            "n_trials":            N_TRIALS,
            "drop_rate_%":         agg("drop_rate"),
            "throughput_rps":      agg("throughput_rps"),
            "latency_p50_ms":      agg("latency_p50_ms"),
            "latency_p95_ms":      agg("latency_p95_ms"),
            "latency_p99_ms":      agg("latency_p99_ms"),
            "latency_mean_ms":     agg("latency_mean_ms"),
            "queue_wait_p50_ms":   agg("queue_wait_p50_ms"),
            "queue_wait_p95_ms":   agg("queue_wait_p95_ms"),
            "spike_drop_rate_%":   agg("spike_drop_rate"),
            "background_drop_rate_%": agg("background_drop_rate"),
        }

        mu = all_configs[label]["drop_rate_%"]["mean"]
        print(f"    → Mean Drop Rate: {mu:.2f}%")

    # Comparative Analysis: Baseline vs New Sweet Spot
    baseline_key = "Old Baseline (Cap=10, Q=0)"
    sdb10_key    = "Old SDB (Cap=10, Q=10)"

    if baseline_key in all_configs and sdb10_key in all_configs:
        baseline_drops = all_configs[baseline_key]["drop_rate_%"]["raw"]
        sdb10_drops    = all_configs[sdb10_key]["drop_rate_%"]["raw"]
        d              = cohen_d(baseline_drops, sdb10_drops)
        relative_reduction = (
            (all_configs[baseline_key]["drop_rate_%"]["mean"] - all_configs[sdb10_key]["drop_rate_%"]["mean"]) /
            max(0.001, all_configs[baseline_key]["drop_rate_%"]["mean"]) * 100
        )
    else:
        d = 0.0
        relative_reduction = 0.0

    # Performance Summary Table
    print("\n  === Performance Summary ===")
    print(f"  {'Config':<28} {'Drop Rate%':>12} {'p95 Lat(ms)':>12} {'Throughput':>12}")
    print(f"  {'-'*28} {'-'*12} {'-'*12} {'-'*12}")
    for label, data in all_configs.items():
        dr  = data["drop_rate_%"]["mean"]
        p95 = data["latency_p95_ms"]["mean"]
        tp  = data["throughput_rps"]["mean"]
        print(f"  {label:<28} {dr:>12.2f} {p95:>12.1f} {tp:>12.2f}")

    print(f"\n  Baseline → SDB Q=10 Drop Rate Reduction: {relative_reduction:.2f}%")
    print(f"  Cohen's d Effect Size: {d:.4f}")
    print("=" * 60)

    return {
        "analysis_type":        "Performance Matrix",
        "timestamp":            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parameters": {
            "n_trials":          N_TRIALS,
            "sim_duration_sec":  SIM_DURATION_SEC,
            "background_rps":    BACKGROUND_RPS,
            "spike_size":        SPIKE_SIZE,
            "spike_interval_sec": SPIKE_INTERVAL_SEC,
            "tb_capacity":       TB_CAPACITY,
            "tb_fill_rate":      TB_FILL_RATE,
            "crn_seed_base":     SEED_BASE,
        },
        "configurations":       all_configs,
        "comparative": {
            "baseline_mean_drop_%": round(all_configs.get(baseline_key, {}).get("drop_rate_%", {}).get("mean", 0), 4),
            "sdb10_mean_drop_%":    round(all_configs.get(sdb10_key, {}).get("drop_rate_%", {}).get("mean", 0), 4),
            "relative_reduction_%": round(relative_reduction, 4),
            "cohens_d":             round(d, 6),
            "effect_magnitude":     "Large" if abs(d) > 0.8 else "Medium" if abs(d) > 0.5 else "Small",
        }
    }


if __name__ == "__main__":
    import os
    result   = run_performance_matrix()
    out_path = os.path.join(os.path.dirname(__file__), "performance_results.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Results saved → {out_path}")
