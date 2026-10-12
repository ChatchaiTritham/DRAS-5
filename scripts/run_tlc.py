"""Regenerate formal/out/*.txt (Table tab:mc and the mutation check) with a pinned TLC.

Downloads tla2tools.jar from the TLA+ release v1.7.4 (TLC 2.19, the version used in the paper)
into formal/ if it is not there, verifies its SHA-256, runs TLC on every configuration
formal/{safe,live}_{10,60,300}_{TRUE,FALSE}.cfg, and runs formal/mutate_spec.py (eight
single-fault mutants, each of which must be rejected).

Requires Java 11+.   Usage: python scripts/run_tlc.py [--workers 8] [--skip-models] [--skip-mutants]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FORMAL = REPO / "formal"
JAR = FORMAL / "tla2tools.jar"
URL = "https://github.com/tlaplus/tlaplus/releases/download/v1.7.4/tla2tools.jar"
SHA256 = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"


def ensure_jar() -> None:
    if not JAR.exists():
        print("downloading", URL)
        urllib.request.urlretrieve(URL, JAR)
    digest = hashlib.sha256(JAR.read_bytes()).hexdigest()
    if digest != SHA256:
        sys.exit(f"tla2tools.jar SHA-256 {digest} != pinned {SHA256}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", default="8")
    ap.add_argument("--skip-models", action="store_true")
    ap.add_argument("--skip-mutants", action="store_true")
    args = ap.parse_args()
    ensure_jar()
    out = FORMAL / "out"
    out.mkdir(exist_ok=True)
    if not args.skip_models:
        for kind in ("safe", "live"):
            for dt in (10, 60, 300):
                for fix in ("TRUE", "FALSE"):
                    cfg = f"{kind}_{dt}_{fix}.cfg"
                    r = subprocess.run(["java", "-cp", str(JAR), "tlc2.TLC", "-workers", args.workers,
                                        "-config", cfg, "DRAS5.tla"], cwd=FORMAL,
                                       capture_output=True, text=True)
                    text = r.stdout + r.stderr
                    (out / cfg.replace(".cfg", ".txt")).write_text(text, encoding="utf-8")
                    last = [ln for ln in text.splitlines() if "distinct states found" in ln or "violated" in ln]
                    print(f"{cfg:22s} {last[-1] if last else text[-200:]}")
    if not args.skip_mutants:
        env = dict(os.environ, TLA2TOOLS=str(JAR))
        r = subprocess.run([sys.executable, "mutate_spec.py"], cwd=FORMAL, capture_output=True, text=True, env=env)
        (out / "mutation.txt").write_text(r.stdout, encoding="utf-8")
        print(r.stdout, r.stderr[-500:])


if __name__ == "__main__":
    main()
