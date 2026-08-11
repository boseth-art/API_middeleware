"""
scalability_test.py
===================
Scalability Tests for Sequential Dual-Bucket (SDB) Traffic Policing Middleware
Author: Boseth Rathnayake | LNBTI
Purpose: Queue saturation curves, horizontal scaling projections, circuit
         breaker stress tests, and sustained load analysis.
"""

import json
import math
import random
import time
import statistics
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Tuple


# ──────────────────────────────────────────────────────────────────────────────
# SIMULATION PARAMETERS
# ──────────────────────────────────────────────────────────────────────────────

SEED               = 42
TB_CAPACITY        = 30
TB_FILL_RATE       = 15.0   # tokens/sec
SIM_DURATION_SEC   = 120.0  # 2 minutes for scalability tests
N_TRIALS           = 10     # Fewer trials for scalability (computationally heavier)


# ──────────────────────────────────────────────────────────────────────────────
# REUSABLE SIMULATION COMPONENTS
# ──────────────────────────────────────────────────────────────────────────────

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


class CircuitBreakerSim:
    def __init__(self, failure_threshold=3, reset_timeout=15.0, success_threshold=2):
        self.failure_threshold = failure_threshold
        self.reset_timeout     = reset_timeout
        self.success_threshold = success_threshold
        self.state             = 'CLOSED'
        self.failures          = 0
        self.successes         = 0
        self.last_failure_time = 0.0
        # Metrics
        self.state_transitions: List[Dict] = []
        self.open_durations:    List[float] = []
        self._open_start:       float = 0.0

    def fire(self, succeed: bool, now: float) -> Tuple[str, str]:
        prev_state = self.state

        if self.state == 'OPEN':
            if now - self.last_failure_time > self.reset_timeout:
                self.open_durations.append(now - self._open_start)
                self.state     = 'HALF_OPEN'
                self.successes = 0
                self.state_transitions.append({"time": now, "from": "OPEN", "to": "HALF_OPEN"})
            else:
                return 'REJECTED', 'OPEN'

        if succeed:
            self.successes += 1
            if self.state == 'HALF_OPEN' and self.successes >= self.success_threshold:
                self.state = 'CLOSED'
                self.failures = 0
                self.successes = 0
                self.state_transitions.append({"time": now, "from": "HALF_OPEN", "to": "CLOSED"})
            elif self.state == 'CLOSED':
                self.failures = 0
            return 'SUCCESS', self.state
        else:
            self.failures          += 1
            self.last_failure_time  = now
            if self.failures >= self.failure_threshold or self.state == 'HALF_OPEN':
                if self.state != 'OPEN':
                    self._open_start = now
                self.state    = 'OPEN'
                self.failures = 0
                self.state_transitions.append({"time": now, "from": prev_state, "to": "OPEN"})
            return 'FAILURE', self.state


# ──────────────────────────────────────────────────────────────────────────────
# TEST 1: QUEUE SATURATION CURVES
# ──────────────────────────────────────────────────────────────────────────────

def test_queue_saturation_curves() -> Dict[str, Any]:
    """
    For queue sizes Q ∈ {5, 10, 20, 50, 100, ∞},
    model drop rate as incoming RPS increases from 5 to 100.
    """
    print("\n  ▶ Queue Saturation Curves ...", flush=True)
    rng        = random.Random(SEED)
    rps_levels = [5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 100, 1000]
    q_sizes    = [0, 5, 10, 20, 50, 75, 100]

    results: Dict[str, Any] = {}

    for q_size in q_sizes:
        label        = "No Queue" if q_size == 0 else f"Q={q_size}"
        rps_results  = {}

        for rps in rps_levels:
            tb = TokenBucketSim(TB_CAPACITY, TB_FILL_RATE)
            queue: List[Tuple[float, int]] = []  # (enqueue_time, req_id)

            served  = 0
            dropped = 0
            queued  = 0

            # Generate Poisson arrivals
            t      = 0.0
            req_id = 0
            arrivals = []
            while t < SIM_DURATION_SEC:
                inter = rng.expovariate(rps)
                t    += inter
                if t < SIM_DURATION_SEC:
                    arrivals.append((t, req_id))
                    req_id += 1

            # Simulate
            drain_cursor = 0.0
            for arrive_t, rid in arrivals:
                if tb.try_consume(arrive_t):
                    served += 1
                elif q_size > 0 and len(queue) < q_size:
                    queue.append((arrive_t, rid))
                    queued += 1
                else:
                    dropped += 1

            # Drain queue
            drain_t = SIM_DURATION_SEC
            while queue:
                enq_t, rid = queue.pop(0)
                drain_t   += 1.0 / TB_FILL_RATE
                if tb.try_consume(drain_t):
                    served += 1
                    queued -= 1
                else:
                    drain_t += 0.5
                    queue.insert(0, (enq_t, rid))

            total    = len(arrivals)
            drop_pct = dropped / total * 100 if total > 0 else 0
            rps_results[rps] = {
                "total":      total,
                "served":     served,
                "dropped":    dropped,
                "drop_rate_%": round(drop_pct, 2),
                "saturation": drop_pct > 50,
            }

        # Find saturation point (first RPS where drop > 30%)
        sat_point = next(
            (rps for rps in rps_levels if rps_results[rps]["drop_rate_%"] > 30),
            None
        )
        results[label] = {
            "queue_size":       q_size,
            "saturation_rps":   sat_point,
            "rps_curve":        rps_results,
        }
        print(f"    {label:<10} saturation at {sat_point} rps")

    return results


# ──────────────────────────────────────────────────────────────────────────────
# TEST 2: HORIZONTAL SCALING PROJECTION
# ──────────────────────────────────────────────────────────────────────────────

def test_horizontal_scaling() -> Dict[str, Any]:
    """
    Model system throughput as worker count scales: 1, 2, 4, 8, 16 workers.
    Each worker processes the queue at TB_FILL_RATE tokens/sec.
    Assumes linear drain speedup (Amdahl's law applied to queue draining).
    """
    print("\n  ▶ Horizontal Scaling Projection ...", flush=True)

    worker_counts    = [1, 2, 4, 8, 16]
    incoming_rps     = 50.0  # sustained load
    queue_size       = 20
    rng              = random.Random(SEED)

    results: Dict[str, Any] = {}

    for workers in worker_counts:
        # Each worker independently drains queue at fill_rate
        combined_drain_rate = TB_FILL_RATE * workers

        tb      = TokenBucketSim(TB_CAPACITY, combined_drain_rate)
        queue   = []
        served  = 0
        dropped = 0

        t = 0.0
        arrivals = []
        while t < SIM_DURATION_SEC:
            inter = rng.expovariate(incoming_rps)
            t    += inter
            if t < SIM_DURATION_SEC:
                arrivals.append(t)

        for arrive_t in arrivals:
            if tb.try_consume(arrive_t):
                served += 1
            elif len(queue) < queue_size:
                queue.append(arrive_t)
            else:
                dropped += 1

        total    = len(arrivals)
        drop_pct = dropped / total * 100 if total > 0 else 0
        tput_rps = served / SIM_DURATION_SEC

        # Efficiency vs single-worker baseline (computed post-loop)
        results[f"{workers}_workers"] = {
            "workers":      workers,
            "drain_rate":   combined_drain_rate,
            "total_reqs":   total,
            "served":       served,
            "dropped":      dropped,
            "drop_rate_%":  round(drop_pct, 2),
            "throughput_rps": round(tput_rps, 2),
        }
        print(f"    Workers={workers:2d}  drain={combined_drain_rate}/s  "
              f"drop={drop_pct:.1f}%  tput={tput_rps:.1f} rps")

    # Compute scaling efficiency
    baseline_tput = results["1_workers"]["throughput_rps"]
    for k, v in results.items():
        workers = v["workers"]
        eff     = (v["throughput_rps"] / (baseline_tput * workers)) * 100 if baseline_tput > 0 else 0
        v["scaling_efficiency_%"] = round(eff, 2)

    return results


# ──────────────────────────────────────────────────────────────────────────────
# TEST 3: CIRCUIT BREAKER STRESS TEST
# ──────────────────────────────────────────────────────────────────────────────

def test_circuit_breaker_stress() -> Dict[str, Any]:
    """
    Two scenarios:
    A) Transient failure: 5-second burst of 80% failure rate, then recovery
    B) Sustained failure: Continuous 60% failure rate for 60 seconds
    C) Cascading failure: Intermittent spikes of 100% failure rate
    """
    print("\n  ▶ Circuit Breaker Stress Tests ...", flush=True)
    rng = random.Random(SEED)

    def simulate_cb_scenario(scenario_name: str, failure_fn) -> Dict[str, Any]:
        cb = CircuitBreakerSim(failure_threshold=3, reset_timeout=15.0, success_threshold=2)

        outcomes = {
            'SUCCESS': 0, 'FAILURE': 0,
            'REJECTED': 0, 'total': 0
        }
        time_in_state = {'CLOSED': 0.0, 'OPEN': 0.0, 'HALF_OPEN': 0.0}
        prev_state    = 'CLOSED'
        prev_t        = 0.0
        t             = 0.0
        req_rate      = 20  # requests per second

        while t < SIM_DURATION_SEC:
            inter    = rng.expovariate(req_rate)
            t       += inter
            if t >= SIM_DURATION_SEC:
                break

            # Accumulate time in state
            time_in_state[prev_state] += t - prev_t
            prev_t     = t

            should_succeed = not failure_fn(t)
            outcome, state = cb.fire(should_succeed, t)
            outcomes[outcome] += 1
            outcomes['total']  += 1
            prev_state = state

        total = max(1, outcomes['total'])
        return {
            "scenario":       scenario_name,
            "total_requests": outcomes['total'],
            "succeeded":      outcomes['SUCCESS'],
            "failed":         outcomes['FAILURE'],
            "rejected":       outcomes['REJECTED'],
            "success_rate_%": round(outcomes['SUCCESS'] / total * 100, 2),
            "rejection_rate_%": round(outcomes['REJECTED'] / total * 100, 2),
            "cb_transitions": cb.state_transitions,
            "n_transitions":  len(cb.state_transitions),
            "time_in_state_sec": {k: round(v, 2) for k, v in time_in_state.items()},
            "open_durations_sec": [round(d, 2) for d in cb.open_durations],
            "mean_open_duration_sec": round(
                statistics.mean(cb.open_durations) if cb.open_durations else 0, 2
            ),
        }

    # Scenario A: Transient spike (0–10s = 80% fail, then recover)
    def transient_failure(t: float) -> bool:
        return t < 10.0 and rng.random() < 0.8

    # Scenario B: Sustained moderate failure (60% throughout)
    rng_b = random.Random(SEED + 1)
    def sustained_failure(t: float) -> bool:
        return rng_b.random() < 0.6

    # Scenario C: Cascading spikes (every 20s, 5s of 100% failure)
    def cascading_failure(t: float) -> bool:
        phase = t % 20.0
        return phase < 5.0

    scenarios = [
        ("A: Transient Burst (80% fail for 10s)", transient_failure),
        ("B: Sustained Moderate (60% fail)",       sustained_failure),
        ("C: Cascading Spikes (100% fail / 20s)",  cascading_failure),
    ]

    results = {}
    for name, fn in scenarios:
        res  = simulate_cb_scenario(name, fn)
        results[name] = res
        print(f"    {name}")
        print(f"      Rejected: {res['rejection_rate_%']:.1f}%  "
              f"Transitions: {res['n_transitions']}  "
              f"Mean OPEN: {res['mean_open_duration_sec']:.1f}s")

    return results


# ──────────────────────────────────────────────────────────────────────────────
# TEST 4: SPIKE ABSORPTION CAPACITY
# ──────────────────────────────────────────────────────────────────────────────

def test_spike_absorption() -> Dict[str, Any]:
    """
    For SDB Q=10, model how much of a sudden spike it can absorb
    as spike size varies from 5 to 200 concurrent requests.
    """
    print("\n  ▶ Spike Absorption Capacity ...", flush=True)
    rng        = random.Random(SEED)
    spike_sizes = [5, 10, 15, 20, 30, 50, 75, 100, 150, 200, 1000]
    q_size      = 75

    results: Dict[str, Any] = {}

    for spike_n in spike_sizes:
        tb      = TokenBucketSim(TB_CAPACITY, TB_FILL_RATE)
        queue   = []
        served  = 0
        dropped = 0
        queued  = 0

        # Background traffic (5 rps for 60 sec)
        t = 0.0
        while t < SIM_DURATION_SEC:
            inter = rng.expovariate(5)
            t    += inter
            if t < SIM_DURATION_SEC:
                if tb.try_consume(t):
                    served += 1
                elif len(queue) < q_size:
                    queue.append(t)
                    queued += 1
                else:
                    dropped += 1

        # Simultaneous spike at t=30s
        for _ in range(spike_n):
            if tb.try_consume(30.0):
                served += 1
            elif len(queue) < q_size:
                queue.append(30.0)
                queued += 1
            else:
                dropped += 1

        total        = served + len(queue) + dropped
        spike_absorbed = min(spike_n, TB_CAPACITY + q_size) / spike_n * 100

        results[f"spike_{spike_n}"] = {
            "spike_size":         spike_n,
            "theoretical_absorb": round(min(spike_n, TB_CAPACITY + q_size) / spike_n * 100, 1),
            "queue_buffered":     min(spike_n, q_size),
            "immediate_service":  min(spike_n, int(TB_CAPACITY)),
            "dropped_spike":      max(0, spike_n - TB_CAPACITY - q_size),
            "drop_rate_%":        round(max(0, spike_n - TB_CAPACITY - q_size) / spike_n * 100, 1),
        }
        print(f"    Spike={spike_n:3d}  absorb={results[f'spike_{spike_n}']['theoretical_absorb']:.0f}%  "
              f"drop={results[f'spike_{spike_n}']['drop_rate_%']:.0f}%")

    return results


# ──────────────────────────────────────────────────────────────────────────────
# TEST 5: SUSTAINED LOAD — TOKEN BUCKET FILL RATE vs DEMAND RATE
# ──────────────────────────────────────────────────────────────────────────────

def test_sustained_load_stability() -> Dict[str, Any]:
    """
    Measure system stability when incoming RPS is a multiple of fill rate:
    RPS ∈ {0.5×, 1×, 1.5×, 2×, 3×, 5×} fill rate
    """
    print("\n  ▶ Sustained Load Stability ...", flush=True)
    rng        = random.Random(SEED)
    multipliers = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    q_size      = 10

    results: Dict[str, Any] = {}

    for mult in multipliers:
        rps     = TB_FILL_RATE * mult
        tb      = TokenBucketSim(TB_CAPACITY, TB_FILL_RATE)
        queue   = []
        served  = 0
        dropped = 0

        t = 0.0
        n = 0
        while t < SIM_DURATION_SEC:
            inter = rng.expovariate(rps)
            t    += inter
            if t >= SIM_DURATION_SEC:
                break
            n += 1
            if tb.try_consume(t):
                served += 1
            elif len(queue) < q_size:
                queue.append(t)
            else:
                dropped += 1

        # Drain queue
        drain_t = SIM_DURATION_SEC
        while queue:
            queue.pop(0)
            drain_t += 1.0 / TB_FILL_RATE
            if tb.try_consume(drain_t):
                served += 1

        total    = n
        drop_pct = dropped / max(1, total) * 100
        tput_rps = served / SIM_DURATION_SEC
        stable   = drop_pct < 5.0

        results[f"{mult}x_fill_rate"] = {
            "incoming_rps":   round(rps, 2),
            "fill_rate":      TB_FILL_RATE,
            "load_ratio":     mult,
            "total_arrivals": total,
            "served":         served,
            "dropped":        dropped,
            "drop_rate_%":    round(drop_pct, 2),
            "throughput_rps": round(tput_rps, 2),
            "stable":         stable,
        }
        print(f"    {mult}× fill rate = {rps} rps  drop={drop_pct:.1f}%  stable={stable}")

    return results


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def run_scalability_tests() -> Dict[str, Any]:
    print("=" * 60)
    print("  SDB Scalability Tests")
    print("=" * 60)

    saturation = test_queue_saturation_curves()
    scaling    = test_horizontal_scaling()
    cb_stress  = test_circuit_breaker_stress()
    absorption = test_spike_absorption()
    stability  = test_sustained_load_stability()

    print("\n  All scalability tests complete.")
    print("=" * 60)

    return {
        "analysis_type":        "Scalability Tests",
        "timestamp":            time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "parameters": {
            "tb_capacity":      TB_CAPACITY,
            "tb_fill_rate":     TB_FILL_RATE,
            "sim_duration_sec": SIM_DURATION_SEC,
            "crn_seed":         SEED,
        },
        "queue_saturation_curves": saturation,
        "horizontal_scaling":      scaling,
        "circuit_breaker_stress":  cb_stress,
        "spike_absorption":        absorption,
        "sustained_load_stability": stability,
    }


if __name__ == "__main__":
    import os
    result   = run_scalability_tests()
    out_path = os.path.join(os.path.dirname(__file__), "scalability_results.json")
    with open(out_path, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n  Results saved → {out_path}")
