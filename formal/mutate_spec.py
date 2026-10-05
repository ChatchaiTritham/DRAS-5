"""Sanity check that the TLC properties have teeth: break the spec one way at a time, expect a violation."""
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
SRC = (HERE / "DRAS5.tla").read_text(encoding="utf-8")
MUTANTS = {
    "C4 gate removed": ("ELSE p3\n      s2", None),   # placeholder, replaced below
}
MUTANTS = {
    "C4 gate removed (Phase 3 skipped)": ("p3   == IF p2 = 5 /\\ s # 5 /\\ ~a THEN 4 ELSE p2", "p3   == p2"),
    "C1 broken (state may fall to the live band)": ("s2   == IF ok THEN s - 1 ELSE p3", "s2   == IF ok THEN s - 1 ELSE IF t < s THEN t ELSE p3"),
    "C5a broken (no cooling window)": ("el >= TCOOL[s] /\\ lc >= Min(TCOOLF[s] + 1, el)", "lc >= 1"),
    "C5b broken (one approval suffices)": ("/\\ m = 1 /\\ p3 = s", "/\\ m # 0 /\\ p3 = s"),
    "C2 broken (timeout late by 3 ticks)": ("el > TMAX[s] /\\ t >= s", "el > TMAX[s] + 3 /\\ t >= s"),
    "C3 broken (no audit entry)": ("/\\ logged' = (s2 # s)", "/\\ logged' = FALSE"),
}
work = HERE / "mut"
work.mkdir(exist_ok=True)
shutil.copy(HERE / "safe_60_TRUE.cfg", work / "safe_60_TRUE.cfg")
for name, (old, new) in MUTANTS.items():
    assert SRC.count(old) == 1, name
    (work / "DRAS5.tla").write_text(SRC.replace(old, new), encoding="utf-8")
    r = subprocess.run(["java", "-cp", str(HERE / "tla2tools.jar"), "tlc2.TLC", "-workers", "8",
                        "-config", "safe_60_TRUE.cfg", "DRAS5.tla"], cwd=work, capture_output=True, text=True)
    out = r.stdout + r.stderr
    m = re.search(r"(Invariant \w+ is violated|Action property \w+ is violated|Temporal properties were violated|No error has been found|Error: [^\n]*)", out)
    print(f"{name:48s} -> {m.group(1) if m else out[-200:]}")
