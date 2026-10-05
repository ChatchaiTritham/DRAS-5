"""Differential conformance test: released state machine vs the TLA+ specification.

formal/DRAS5.tla was written from the manuscript, not from this code. Here a line-by-line
Python transcription of its Step relation (FIX = TRUE) is driven by the same inputs as the
released machine. Whatever the machine does with rho_eff (the exponential decay) is read off
the machine and fed to the model as the nondeterministic `effNew`, after checking that it lies
in the set the model allows. The two level sequences must then agree on every step.

Output: results/tla_conformance.json.   Usage: python scripts/tla_conformance.py [--n 60000]
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from collections import Counter
from pathlib import Path

logging.disable(logging.CRITICAL)
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import RiskState, risk_to_state  # noqa: E402

TICKS = {10: dict(tmax=(999, 30, 12, 6, 999), tcool=(0, 60, 30, 18, 0), tcoolf=(0, 60, 30, 18, 0), cap=61),
         60: dict(tmax=(999, 5, 2, 1, 999), tcool=(0, 10, 5, 3, 0), tcoolf=(0, 10, 5, 3, 0), cap=12),
         300: dict(tmax=(999, 1, 0, 0, 999), tcool=(0, 2, 1, 1, 0), tcoolf=(0, 2, 1, 0, 0), cap=4)}
RHOS = (0.0, 0.29, 0.30, 0.49, 0.50, 0.69, 0.70, 0.89, 0.90, 1.0)


def dec_band(k):             # FIX = TRUE
    return 1 if k == 2 else k - 2


def tla_step(st, t, a, m, eff_new, cfg):
    """Transcription of `Step` in DRAS5.tla. st = (s, dwell, eff, low). Returns new tuple."""
    s, dwell, eff, low = st
    tmax, tcool, cap = cfg["tmax"], cfg["tcool"], cfg["cap"]
    el = dwell + 1
    p1 = s + 1 if (s not in (1, 5) and el > tmax[s - 1] and t >= s and (s != 4 or a)) else s
    p2 = max(p1, t)
    p3 = 4 if (p2 == 5 and s != 5 and not a) else p2
    lc = min(low + 1, cap) if (s in (2, 3, 4) and eff_new <= dec_band(s)) else 0
    ok = (m == 1 and p3 == s and s not in (1, 5) and el >= tcool[s - 1] and lc >= min(cfg["tcoolf"][s - 1] + 1, el))
    s2 = s - 1 if ok else p3
    if s2 != s:
        return (s2, 0, t, 0)
    return (s2, min(dwell + 1, cap), eff_new, lc)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60000)
    args = ap.parse_args()
    rng = random.Random(2026)
    tally = Counter()
    examples = []
    for dt, cfg in TICKS.items():
        for _ in range(args.n // len(TICKS)):
            sm = DRAS5StateMachine(enable_constraints=True, enable_audit=False, require_human_approval=True)
            st = (1, 0, 1, 0)
            seq = []
            while len(seq) < 30:
                seq.extend([(rng.choice(RHOS), rng.random() < 0.5, rng.choice((0, 1, 1, 2, 3)))] * rng.randint(1, 8))
            for i, (rho, a, m) in enumerate(seq[:30]):
                kw = {1: dict(approval_1=True, approval_2=True, approver_1="a", approver_2="b"),
                      2: dict(approval_1=True, approval_2=False, approver_1="a", approver_2="b"),
                      3: dict(approval_1=True, approval_2=True, approver_1="a", approver_2="a"),
                      0: {}}[m]
                old = int(sm.current_state)
                new = int(sm.update(risk_score=rho, t=i * float(dt), human_approved=a,
                                    deescalation_request=m != 0, **kw))
                t = int(risk_to_state(rho))
                if new != old:
                    eff_new = t
                else:
                    eff_new = int(risk_to_state(sm._rho_eff_history[-1]))
                s, dwell, eff, low = st
                allowed = {t} if t > eff else set(range(t, eff + 1))
                tally["steps"] += 1
                if eff_new not in allowed:
                    tally["abstraction_violation"] += 1
                    if len(examples) < 8:
                        examples.append(dict(kind="eff outside model's allowed set", dt=dt, i=i,
                                             rho=rho, model_eff=eff, code_eff=eff_new))
                    eff_new = max(t, min(eff_new, eff))
                prev_st = st
                st = tla_step(st, t, a, m, eff_new, cfg)
                if st[0] != new:
                    if new == old and st[0] == old - 1 and m == 1:
                        # the spec allows this C5 grant, the code withholds it: the code adds the
                        # requirement that the effective-risk window be non-increasing
                        tally["code_stricter_than_spec"] += 1
                    else:
                        tally["level_mismatch"] += 1
                        if len(examples) < 8:
                            examples.append(dict(kind="level mismatch", dt=dt, i=i, rho=rho, alpha=a,
                                                 mode=m, code=new, model=st[0], before=old))
                    break                      # first divergence ends this sequence (no cascade)
    out = dict(tally), examples
    (REPO / "results" / "tla_conformance.json").write_text(
        json.dumps(dict(tally=dict(tally), examples=examples), indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(tally=dict(tally), examples=examples), indent=1))


if __name__ == "__main__":
    main()
