---------------------------- MODULE DRAS5 ----------------------------
(***************************************************************************)
(* Specification of DRAS-5 drafted from the manuscript (Algorithm 1,      *)
(* Eqs. 1-5, Definitions C1-C5). It is NOT independent of the Python code: *)
(* the drafter had read the code, and two conventions (timeout compared    *)
(* with ">", cooling-window size) were aligned to the code after the       *)
(* differential test scripts/tla_conformance.py. C3, C5(a) and C5(b) are   *)
(* near-restatements of guards in Step; C1, C2, C4, Reach and Cor1 carry   *)
(* the content.                                                            *)
(*                                                                         *)
(* Abstraction. The risk score is replaced by its band tau in 1..5 (the     *)
(* five intervals of Eq. 2). The effective risk rho_eff is replaced by its *)
(* band `eff`: eff never falls below the live band and may fall by any      *)
(* amount per tick (an over-approximation of ANY decay schedule), so every  *)
(* safety property proved here holds for every decay rate. "rho_eff <       *)
(* theta_j" becomes "eff <= j-1". Time is counted in sampling ticks.        *)
(***************************************************************************)
EXTENDS Naturals

CONSTANTS DT,        \* sampling interval in seconds: 10, 60 or 300
          FIX,       \* FALSE: paper as written; TRUE: S2->S1 uses theta_2 (see DecBand)
          CAP        \* counter cap

\* Table 2 in ticks; 999 stands for "no timeout" (S1, S5). The timeout fires when the dwell
\* in seconds EXCEEDS T_max, i.e. dwell ticks > floor(T_max / DT).
TMAX  == CASE DT = 10  -> <<999, 30, 12, 6, 999>>
           [] DT = 60  -> <<999, 5, 2, 1, 999>>
           [] DT = 300 -> <<999, 1, 0, 0, 999>>
\* TCOOL: ceil(T_cool / DT), the ticks a grant must have spent in the state.
\* TCOOLF: floor(T_cool / DT); the window holds TCOOLF + 1 samples, capped at those since entry.
TCOOL  == CASE DT = 10  -> <<0, 60, 30, 18, 0>>
            [] DT = 60  -> <<0, 10, 5, 3, 0>>
            [] DT = 300 -> <<0, 2, 1, 1, 0>>
TCOOLF == CASE DT = 10  -> <<0, 60, 30, 18, 0>>
            [] DT = 60  -> <<0, 10, 5, 3, 0>>
            [] DT = 300 -> <<0, 2, 1, 0, 0>>

VARIABLES s,         \* state level 1..5
          dwell,     \* ticks since entering s (capped)
          eff,       \* band of rho_eff
          low,       \* consecutive samples with rho_eff below the de-escalation threshold
          maxreg,    \* highest REGISTERED input level so far (C4 cap applied)
          maxs,      \* highest level the machine has reached
          granted,   \* ghost: the last step was a C5 grant
          logged,    \* ghost: the last step wrote an audit entry
          prev,      \* ghost: level before the last step
          tin, ain, min   \* ghost: the inputs of the last step (band, S5 approval, request mode)

vars == <<s, dwell, eff, low, maxreg, maxs, granted, logged, prev, tin, ain, min>>

Min(a, b) == IF a < b THEN a ELSE b
Max(a, b) == IF a > b THEN a ELSE b

\* Largest band of rho_eff that still satisfies rho_eff < theta_{k-1} (Def. C5, item 1).
\* For k = 2 the paper's threshold is theta_1 = 0, which no rho_eff >= 0 can satisfy.
DecBand(k) == IF k = 2 THEN (IF FIX THEN 1 ELSE 0) ELSE k - 2

Init == /\ s = 1 /\ dwell = 0 /\ eff = 1 /\ low = 0
        /\ maxreg = 1 /\ maxs = 1 /\ granted = FALSE /\ logged = FALSE /\ prev = 1
        /\ tin = 1 /\ ain = FALSE /\ min = 0

\* One sample: band t, approval alpha for S5, request mode m
\*   0 no request, 1 two distinct approvals, 2 one approval missing, 3 same approver twice
Step(t, a, m, effNew) ==
  LET el   == dwell + 1                                       \* ticks since entry at this sample
      p1   == IF s \notin {1, 5} /\ el > TMAX[s] /\ t >= s /\ (s # 4 \/ a)
              THEN s + 1 ELSE s                               \* Phase 1: timeout (C2)
      p2   == Max(p1, t)                                      \* Phase 2: escalation (C1)
      p3   == IF p2 = 5 /\ s # 5 /\ ~a THEN 4 ELSE p2         \* Phase 3: approval gate (C4)
      lc   == IF s \in 2..4 /\ effNew <= DecBand(s) THEN Min(low + 1, CAP) ELSE 0
      ok   == /\ m = 1 /\ p3 = s /\ s \notin {1, 5}
              /\ el >= TCOOL[s] /\ lc >= Min(TCOOLF[s] + 1, el)   \* Phase 4: full window (C5a)
      s2   == IF ok THEN s - 1 ELSE p3
  IN /\ s' = s2
     /\ granted' = ok
     /\ logged' = (s2 # s)                                    \* Phase 5: audit (C3)
     /\ prev' = s
     /\ tin' = t /\ ain' = a /\ min' = m
     /\ dwell' = IF s2 # s THEN 0 ELSE Min(dwell + 1, CAP)
     /\ eff' = IF s2 # s THEN t ELSE effNew
     /\ low' = IF s2 # s THEN 0 ELSE lc
     /\ maxreg' = Max(maxreg, IF t = 5 /\ ~a THEN 4 ELSE t)
     /\ maxs' = Max(maxs, s2)

Next == \E t \in 1..5, a \in BOOLEAN, m \in 0..3 :
          \E e \in (IF t > eff THEN {t} ELSE t..eff) : Step(t, a, m, e)

Spec == Init /\ [][Next]_vars

TypeOK == /\ s \in 1..5 /\ eff \in 1..5 /\ dwell \in 0..CAP /\ low \in 0..CAP

(************************ properties of the paper ************************)
\* C1 / Theorem 1 : the level never decreases except on a C5 grant
C1 == [][ s' >= s \/ granted' ]_vars
\* C5(c): a decrease is exactly one level
C5c == [][ s' < s => s' = s - 1 ]_vars
\* C5(b): a decrease needs a request carrying two distinct approvals
C5b == [][ s' < s => min' = 1 ]_vars
\* C5(a): a grant needs the full cooling window since entry
C5a == [][ granted' => dwell + 1 >= TCOOL[s] ]_vars
\* C2 / Theorem 2 : an S2/S3 sample past the timeout with tau >= s does not leave the level in place
C2 == [][ (s \in {2, 3} /\ dwell + 1 > TMAX[s] /\ tin' >= s) => s' > s ]_vars
\* C3 / Theorem 3 : every change of level writes an audit entry
C3 == [][ s' # s => logged' ]_vars
\* C4 / Theorem 4 : no step enters S5 without approval
C4 == [][ (s' = 5 /\ s # 5) => ain' ]_vars

\* Reach (Theorem 1, input-relative): the highest level reached is at least the highest
\* registered input level.
Reach == maxs >= maxreg

(*************** liveness instance for Corollary 1 ***********************)
\* rho = 0 forever (tau = 1), two distinct approvals always supplied; rho_eff decays
\* (fairly) until it reaches the live band.
LiveInit == /\ s \in 2..4 /\ dwell = 0 /\ eff = s /\ low = 0
            /\ maxreg = s /\ maxs = s /\ granted = FALSE /\ logged = FALSE /\ prev = s
            /\ tin = 1 /\ ain = FALSE /\ min = 0
LiveNext == \E e \in 1..eff : Step(1, TRUE, 1, e)
Decay == LiveNext /\ eff' < eff
LiveSpec == LiveInit /\ [][LiveNext]_vars /\ WF_vars(Decay) /\ WF_vars(LiveNext)
Cor1 == <>(s = 1)
=============================================================================
