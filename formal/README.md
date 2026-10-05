# Formal specification of DRAS-5 (TLA+)

`DRAS5.tla` is written from the manuscript (Algorithm 1, Eqs. 1-5, Definitions C1-C5), not from the Python code.
It abstracts the risk score and the effective risk to their bands; the effective risk may fall by any amount per
tick, so every property holds for every decay schedule. `FIX = FALSE` is the paper as first written (S2->S1 uses
theta_1 = 0, which makes S1 unreachable); `FIX = TRUE` is the corrected rule used by the released code.

Run (Java 17+, TLC from https://github.com/tlaplus/tlaplus/releases):

    java -cp tla2tools.jar tlc2.TLC -workers 8 -config safe_60_TRUE.cfg DRAS5.tla   # C1-C5 + reach
    java -cp tla2tools.jar tlc2.TLC -workers 8 -config live_60_FALSE.cfg DRAS5.tla  # Corollary 1: counterexample
    python mutate_spec.py                                                          # six broken specs must all fail

Config names: `safe|live_<sampling interval in s>_<FIX>.cfg`. Outputs of the runs in the paper are in `out/`.
`../scripts/tla_conformance.py` ties the released implementation to this specification by differential testing.
