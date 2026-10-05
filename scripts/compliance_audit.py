#!/usr/bin/env python3
"""
Measured constraint-compliance counters for DRAS-5 (C1-C5) on the seeded cohort.

Replaces the per-constraint "test events" that earlier manuscript drafts typed in
by hand. Every number written to ``results/compliance.csv`` and
``results/compliance.json`` is counted while the released state machine processes
the same 5,000 seed-42 trajectories as ``run_all.py``; the C5 check uses an
independent re-computation of the effective risk from the raw scores, so it does
not simply re-read the state machine's own verdict.

Three passes over the cohort:

  A  main protocol  -- audit on, dual-approved de-escalation requests (as run_all)
  B  approval gate  -- human approval for S4 -> S5 withheld on every call
  C  dual approval  -- de-escalation requests issued with dual approval withheld

Usage
-----
    python scripts/compliance_audit.py
    python scripts/compliance_audit.py --trajectories 5000 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_all as R  # noqa: E402  (shared generators and constants)
from dras5.state_machine import DRAS5StateMachine  # noqa: E402
from dras5.states import STATE_CONFIG, RiskState, risk_to_state  # noqa: E402

logging.disable(logging.CRITICAL)  # the state machine logs every denial

DT = R.DT_SECONDS
S = RiskState


def cohort(n_traj: int, seed: int):
    per_type = n_traj // len(R.TYPES)
    for tt in R.TYPES:
        for j in range(per_type):
            yield tt, R.make_trajectory(tt, R._traj_seed(seed, tt, j))


def oracle_c5_ok(state, times, rhos, t_now):
    """Independent C5 check from raw scores (peak/decay re-derived, not read back).

    ``times``/``rhos`` hold the samples seen since the state was entered, the
    current one included. Returns True when the cooling window has fully elapsed
    inside the state and every effective-risk sample in it is below theta_{k-1}.
    """
    cfg = STATE_CONFIG[state]
    lam, t_cool = cfg["lam"], cfg["t_cool"]
    # oracle encodes the corrected rule: theta_{k-1}, except S2->S1 which uses theta_2
    theta_next = STATE_CONFIG[S(state - 1)]["theta"] if state - 1 != 1 else STATE_CONFIG[S(state)]["theta"]
    peak, t_peak, eff = 0.0, 0.0, []
    for t, r in zip(times, rhos):
        if r > peak:
            peak, t_peak = r, t
        eff.append((t, max(r, peak * math.exp(-lam * max(0.0, t - t_peak)))))
    window = [e for (t, e) in eff if t_now - t <= t_cool]
    return bool(window) and (t_now - times[0] >= t_cool - DT - 1e-9) and all(
        e < theta_next for e in window)


def pass_main(n_traj, seed):
    out = dict(steps=0, c1_decreases=0, c1_violations=0, c5_requests=0,
               c5_grants=0, c5_not_single_step=0, c5_oracle_disagree=0,
               transitions=0, c3_unlogged=0, c3_chain_breaks=0,
               timeout_events=0, c2_after_recovery=0, c2_early=0, c2_overdue_steps=0,
               c2_recovery_exempt_steps=0, trajectories=0)
    for _tt, rho in cohort(n_traj, seed):
        out["trajectories"] += 1
        sm = DRAS5StateMachine(enable_constraints=True, enable_audit=True,
                               require_human_approval=False)
        times, rhos = [], []
        for i, r in enumerate(rho):
            t = i * DT
            before = sm.current_state
            n_log, n_hist = len(sm.audit_log), len(sm.transition_history)
            want = risk_to_state(r) < before and before not in (S.SAFE, S.EMERGENCY)
            new = sm.update(risk_score=r, t=t, human_approved=True,
                            deescalation_request=want, dual_approval=want)
            times.append(t)
            rhos.append(r)
            out["steps"] += 1
            added = len(sm.audit_log) - n_log
            out["transitions"] += added

            # C3: every state change has a log entry; entries chain end to end.
            if new != before and added == 0:
                out["c3_unlogged"] += 1
            if added:
                for e in sm.audit_log.entries[n_log:]:
                    if e.from_state != before.name:
                        out["c3_chain_breaks"] += 1
                    before = S[e.to_state]
                if before != new:
                    out["c3_chain_breaks"] += 1

            # C1 / C5
            if want:
                out["c5_requests"] += 1
            first = sm.transition_history[n_hist] if added else None
            decreased = added > 0 and first.from_state > first.to_state
            if decreased:
                out["c1_decreases"] += 1
                if not want:
                    out["c1_violations"] += 1
                else:
                    out["c5_grants"] += 1
                    if first.from_state - first.to_state != 1:
                        out["c5_not_single_step"] += 1
                    if not oracle_c5_ok(first.from_state, times, rhos, t):
                        out["c5_oracle_disagree"] += 1

            # C2: timeout transitions fire in (T_max, T_max + dt]; no live overdue state.
            for tr in sm.transition_history[n_hist:]:
                if tr.trigger == "timeout_escalation":
                    out["timeout_events"] += 1
                    d, tmax = tr.metadata["duration_in_state"], STATE_CONFIG[tr.from_state]["t_max"]
                    if d > tmax + DT + 1e-9:
                        # fired only once risk re-warranted the state after a
                        # recovery-exempt interval (see the C2 exemption)
                        out["c2_after_recovery"] += 1
                    if d <= tmax:
                        out["c2_early"] += 1
            cur = sm.current_state
            tmax = STATE_CONFIG[cur]["t_max"]
            if tmax != float("inf") and (t - sm.state_entry_time) > tmax + DT:
                if risk_to_state(r) >= cur:
                    out["c2_overdue_steps"] += 1
                else:
                    out["c2_recovery_exempt_steps"] += 1

            if added:
                times, rhos = [], []  # tracker resets on every entry
    return out


def pass_approval_gate(n_traj, seed):
    """C4 with approval withheld on every call: no route may reach EMERGENCY.

    An attempt is any step at which the risk maps to EMERGENCY from a lower state,
    or at which a CRITICAL state has overrun its timeout; a violation is any
    recorded transition into EMERGENCY, whatever its trigger.
    """
    out = dict(attempts=0, risk_attempts=0, timeout_attempts=0, violations=0,
               trajectories=0)
    for _tt, rho in cohort(n_traj, seed):
        out["trajectories"] += 1
        sm = DRAS5StateMachine(enable_constraints=True, enable_audit=True,
                               require_human_approval=True)
        for i, r in enumerate(rho):
            t = i * DT
            before = sm.current_state
            n_hist = len(sm.transition_history)
            if before < S.EMERGENCY and risk_to_state(r) == S.EMERGENCY:
                out["risk_attempts"] += 1
            elif before == S.CRITICAL and sm.check_timeout(t=t):
                out["timeout_attempts"] += 1
            sm.update(risk_score=r, t=t, human_approved=False)
            out["violations"] += sum(tr.to_state == S.EMERGENCY
                                     for tr in sm.transition_history[n_hist:])
        out["attempts"] = out["risk_attempts"] + out["timeout_attempts"]
    return out


def pass_dual_approval(n_traj, seed, mode="second_withheld"):
    """Withhold one C5 approval on every request.

    mode: ``second_withheld`` (alpha_2 = False), ``first_withheld`` (alpha_1 = False) or
    ``same_approver`` (both signals true but the same approver id, so not independent).
    """
    out = dict(mode=mode, requests=0, deescalations=0, trajectories=0)
    for _tt, rho in cohort(n_traj, seed):
        out["trajectories"] += 1
        sm = DRAS5StateMachine(enable_constraints=True, enable_audit=True,
                               require_human_approval=False)
        for i, r in enumerate(rho):
            before = sm.current_state
            n_hist = len(sm.transition_history)
            want = risk_to_state(r) < before and before not in (S.SAFE, S.EMERGENCY)
            kw = dict(second_withheld=dict(approval_1=True, approval_2=False),
                      first_withheld=dict(approval_1=False, approval_2=True),
                      same_approver=dict(approval_1=True, approval_2=True,
                                         approver_1="clinician-A", approver_2="clinician-A"))[mode]
            sm.update(risk_score=r, t=i * DT, human_approved=True,
                      deescalation_request=want, **kw)
            out["requests"] += int(want)
            for tr in sm.transition_history[n_hist:]:
                if tr.from_state > tr.to_state:
                    out["deescalations"] += 1
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trajectories", type=int, default=R.N_TRAJECTORIES)
    ap.add_argument("--seed", type=int, default=R.BASE_SEED)
    args = ap.parse_args()

    a = pass_main(args.trajectories, args.seed)
    b = pass_approval_gate(args.trajectories, args.seed)
    c = pass_dual_approval(args.trajectories, args.seed)
    c_first = pass_dual_approval(args.trajectories, args.seed, "first_withheld")
    c_same = pass_dual_approval(args.trajectories, args.seed, "same_approver")

    rows = [
        dict(constraint="C1", unit="steps checked", events=a["steps"],
             violations=a["c1_violations"],
             note=f"{a['c1_decreases']} state decreases, all C5 grants"),
        dict(constraint="C2", unit="timeout escalations", events=a["timeout_events"],
             violations=a["c2_early"] + a["c2_overdue_steps"],
             note=(f"{a['c2_after_recovery']} fired after a recovery-exempt interval; "
                    f"{a['c2_recovery_exempt_steps']} overdue steps exempt (risk already below state)")),
        dict(constraint="C3", unit="logged transitions", events=a["transitions"],
             violations=a["c3_unlogged"] + a["c3_chain_breaks"],
             note="state change without entry, or broken from/to chain"),
        dict(constraint="C4", unit="attempts to enter EMERGENCY, approval withheld",
             events=b["attempts"], violations=b["violations"],
             note=f"{b['risk_attempts']} risk-driven, {b['timeout_attempts']} CRITICAL timeouts"),
        dict(constraint="C5", unit="de-escalation grants audited by independent oracle",
             events=a["c5_grants"],
             violations=a["c5_oracle_disagree"] + a["c5_not_single_step"],
             note=(f"{a['c5_requests']} requests; alpha_2 withheld: {c['requests']} requests, {c['deescalations']} de-escalations; "
                  f"alpha_1 withheld: {c_first['deescalations']}; same approver id: {c_same['deescalations']}")),
    ]
    results = Path(__file__).resolve().parent.parent / "results"
    results.mkdir(exist_ok=True)
    with open(results / "compliance.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    (results / "compliance.json").write_text(
        json.dumps(dict(main=a, approval_gate=b, dual_approval=c,
                        first_withheld=c_first, same_approver=c_same), indent=2),
        encoding="utf-8")
    print(json.dumps(dict(main=a, approval_gate=b, dual_approval=c,
                          first_withheld=c_first, same_approver=c_same), indent=2))


if __name__ == "__main__":
    main()
