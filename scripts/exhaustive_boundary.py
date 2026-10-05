"""Boundary-alphabet exhaustive + deep randomised check of the released state machine.

Complements scripts/revision_metrics.py (band-representative alphabet, length 4). Here the
alphabet sits on each threshold (theta-eps and theta, plus 0 and 1), because off-by-one errors
live on the boundary, and the checked properties include the timeout and the C5 guards:

  C1   a decrease only on a C5 request, exactly one level
  C2   in S2/S3, once the dwell time reaches T_max and tau(rho) >= s, the step does not end in s
  C4   no step enters S5 without alpha
  C5   a decrease needs both approvals from distinct approvers, a request, and a full cooling
       window since entry
  reach  the highest level reached >= the highest registered input level (C4 cap applied)

Part 1: every sequence of length L over the alphabet at each sampling interval (exhaustive).
Part 2: seeded random sequences of length 15 at the same intervals (deep, not exhaustive).

Output: results/exhaustive_boundary.json.  Usage: python scripts/exhaustive_boundary.py [--len 4]
"""
from __future__ import annotations

import argparse
import itertools
import json
import logging
import multiprocessing as mp
import random
import sys
from pathlib import Path

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import RiskState, STATE_CONFIG, risk_to_state  # noqa: E402

EPS = 0.01
RHOS = (0.0, 0.30 - EPS, 0.30, 0.50 - EPS, 0.50, 0.70 - EPS, 0.70, 0.90 - EPS, 0.90, 1.0)
# approval mode: 0 no request, 1 request with both approvers, 2 request with alpha_2 missing,
# 3 request with the same approver twice
MODES = (0, 1, 2, 3)
SYMBOLS = [(r, a, m) for r in RHOS for a in (0, 1) for m in MODES]
DTS = (10.0, 60.0, 300.0)
# Cooling windows as shipped: the checker must not read the (possibly mutated) live config.
ORIG_T_COOL = {k: v.get("t_cool") or 0.0 for k, v in STATE_CONFIG.items()}
ORIG_T_MAX = {k: v["t_max"] for k, v in STATE_CONFIG.items()}


MUTANTS = ("none", "c4_gate_off", "c1_monotonic_off", "ignore_alpha2", "ignore_independence",
           "no_cooling_window", "timeout_off")


def make_machine(mutant):
    """The released machine, or one deliberately broken in a single way."""
    sm = DRAS5StateMachine(enable_constraints=mutant != "c1_monotonic_off", enable_audit=False,
                           require_human_approval=mutant != "c4_gate_off")
    if mutant == "timeout_off":
        sm._check_and_auto_escalate = lambda *a, **k: None
    return sm


def run(seq, dt, mutant="none"):
    """Return violation counters and coverage counters for one input sequence."""
    sm = make_machine(mutant)
    saved = dict(STATE_CONFIG)
    prev, entry_t, reach, need = RiskState.SAFE, 0.0, 0, 0
    v = dict(c1=0, c2=0, c4=0, c5=0, reach=0, cov_grant=0, cov_timeout=0, cov_c4_block=0,
             cov_c5_denied=0)
    for i, (rho, alpha, mode) in enumerate(seq):
        t = i * dt
        kw = {}
        if mode == 1:
            kw = dict(approval_1=True, approval_2=True, approver_1="a", approver_2="b")
        elif mode == 2:
            kw = dict(approval_1=True, approval_2=False, approver_1="a", approver_2="b")
        elif mode == 3:
            kw = dict(approval_1=True, approval_2=True, approver_1="a", approver_2="a")
        if mutant == "ignore_alpha2" and kw:
            kw["approval_2"] = True
        if mutant == "ignore_independence" and kw:
            kw["approver_2"] = "b"
        if mutant == "no_cooling_window":
            for k in STATE_CONFIG:
                if STATE_CONFIG[k].get("t_cool") is not None:
                    STATE_CONFIG[k]["t_cool"] = 0.0
        new = sm.update(risk_score=rho, t=t, human_approved=bool(alpha),
                        deescalation_request=mode != 0, **kw)
        tau = risk_to_state(rho)
        if new < prev:
            v["cov_grant"] += 1
        elif mode != 0 and tau < prev and prev not in (RiskState.SAFE, RiskState.EMERGENCY):
            v["cov_c5_denied"] += 1
        if new > prev and new > tau:
            v["cov_timeout"] += 1                         # raised above the risk-implied level
        if tau == RiskState.EMERGENCY and not alpha and new < RiskState.EMERGENCY:
            v["cov_c4_block"] += 1
        dwell = t - entry_t
        if new < prev:
            if mode != 1:
                v["c1"] += 1; v["c5"] += 1               # decrease without two independent approvals
            if prev - new != 1:
                v["c1"] += 1
            t_cool = ORIG_T_COOL[prev]
            if dwell + 1e-9 < t_cool:
                v["c5"] += 1                              # decrease before the cooling window elapsed
        if new == RiskState.EMERGENCY and prev != RiskState.EMERGENCY and not alpha:
            v["c4"] += 1
        if prev in (RiskState.MONITOR, RiskState.ALERT) and tau >= prev and new == prev:
            t_max = ORIG_T_MAX[prev]
            # dwell is measured to the previous sample; the machine may use this sample's time
            if t - entry_t >= t_max + 1e-9 and tau >= prev:
                v["c2"] += 1
        need = max(need, int(tau) if (int(tau) < 5 or alpha) else 4)
        reach = max(reach, int(new))
        if new != prev:
            entry_t = t
        prev = new
    v["reach"] += int(reach < need)
    for k, val in saved.items():
        STATE_CONFIG[k].update(val)
    return v


def _tally(acc, v):
    for k, x in v.items():
        acc[k] = acc.get(k, 0) + x


def exhaustive_chunk(args):
    first, length, dt = args
    acc = dict(c1=0, c2=0, c4=0, c5=0, reach=0, n=0)
    for tail in itertools.product(SYMBOLS, repeat=length - 1):
        _tally(acc, {k: x for k, x in run((first,) + tail, dt).items() if not k.startswith("cov_")})
        acc["n"] += 1
    return acc


def random_chunk(args):
    seed, count, length, dt = args
    rng = random.Random(seed)
    acc = dict(c1=0, c2=0, c4=0, c5=0, reach=0, n=0)
    for _ in range(count):
        # dwell: repeat each symbol 1-4 times so that windows and timeouts can complete
        seq = []
        while len(seq) < length:
            s = rng.choice(SYMBOLS)
            seq.extend([s] * rng.randint(1, 4))
        _tally(acc, run(tuple(seq[:length]), dt))
        acc["n"] += 1
    return acc


def coverage_chunk(args):
    seed, count, length, dt, mutant = args
    rng = random.Random(seed)
    acc = {}
    for _ in range(count):
        seq = []
        while len(seq) < length:
            s_ = rng.choice(SYMBOLS)
            seq.extend([s_] * rng.randint(1, 12 if dt <= 10 else 4))
        v = run(tuple(seq[:length]), dt, mutant)
        for k, x in v.items():
            acc[k] = acc.get(k, 0) + x
        acc["n"] = acc.get("n", 0) + 1
        for k in ("cov_grant", "cov_timeout", "cov_c4_block", "cov_c5_denied"):
            acc["seq_" + k] = acc.get("seq_" + k, 0) + int(v[k] > 0)
    return acc


def coverage_and_mutation(count=48000) -> dict:
    """Part 3: how often each guard fires, and whether the checker catches seeded bugs."""
    out = {"coverage": [], "mutation": []}
    cfgs = [(10.0, 60), (60.0, 15), (300.0, 15)]
    with mp.Pool() as pool:
        for dt, length in cfgs:
            parts = pool.map(coverage_chunk, [(5000 + k, count // 24, length, dt, "none") for k in range(24)])
            tot = {k: sum(p.get(k, 0) for p in parts) for k in parts[0]}
            out["coverage"].append({"dt_s": dt, "length": length, **tot})
            print("coverage", dt, tot, flush=True)
        for m in MUTANTS[1:]:
            row = {"mutant": m}
            for dt, length in cfgs:
                parts = pool.map(coverage_chunk, [(9000 + k, count // 24, length, dt, m) for k in range(24)])
                row[f"dt{int(dt)}"] = {k: sum(p.get(k, 0) for p in parts) for k in ("c1", "c2", "c4", "c5", "reach")}
            row["detected"] = any(sum(d.values()) > 0 for k, d in row.items() if k.startswith("dt"))
            out["mutation"].append(row)
            print("mutant", m, row, flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--coverage", action="store_true", help="run part 3 only")
    ap.add_argument("--len", type=int, default=4)
    ap.add_argument("--random", type=int, default=60000, help="random sequences per interval")
    args = ap.parse_args()
    if args.coverage:
        res = coverage_and_mutation()
        (REPO / "results" / "exhaustive_coverage_mutation.json").write_text(
            json.dumps(res, indent=2) + "\n", encoding="utf-8")
        return
    out = {"alphabet": len(SYMBOLS), "exhaustive_length": args.len, "exhaustive": [], "random": []}
    with mp.Pool() as pool:
        for dt in DTS:
            parts = pool.map(exhaustive_chunk, [(s, args.len, dt) for s in SYMBOLS])
            tot = {k: sum(p[k] for p in parts) for k in parts[0]}
            out["exhaustive"].append({"dt_s": dt, **tot})
            print("exhaustive", dt, tot, flush=True)
        for dt in DTS:
            jobs = [(1000 + k, args.random // 24, 15, dt) for k in range(24)]
            parts = pool.map(random_chunk, jobs)
            tot = {k: sum(p[k] for p in parts) for k in parts[0]}
            out["random"].append({"dt_s": dt, "length": 15, **tot})
            print("random", dt, tot, flush=True)
    (REPO / "results" / "exhaustive_boundary.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
