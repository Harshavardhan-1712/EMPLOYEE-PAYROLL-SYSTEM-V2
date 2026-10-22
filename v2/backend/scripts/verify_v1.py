"""Verify that V1's files are byte-identical to the baseline recorded before V2 was built.

    python -m scripts.verify_v1

Reads docs/v1-baseline.sha256 (SHA-256 of every V1 file) and compares each file under the repository root.
Files V1 creates when you *run* it (employee_data.db, exports/, reports/) are reported but are not a failure.
Exit code: 0 = all V1 files unchanged, 1 = a V1 file is missing or modified.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from app.config import V1_ROOT

BASELINE = Path(__file__).resolve().parent.parent.parent / "docs" / "v1-baseline.sha256"
RUNTIME_ARTIFACTS = {"employee_data.db", "exports", "reports", "__pycache__"}


def parse_baseline(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.strip():
            digest, _, name = line.partition("  ")
            out[name.strip().removeprefix("./")] = digest.strip()
    return out


def check(root: Path = V1_ROOT, baseline: Path = BASELINE) -> tuple[list[str], list[str], list[str]]:
    """returns (ok, problems, runtime_artifacts_present)"""
    expected = parse_baseline(baseline.read_text(encoding="utf-8"))
    ok, bad = [], []
    for name, digest in sorted(expected.items()):
        f = root / name
        if not f.is_file():
            bad.append(f"MISSING   {name}")
        elif hashlib.sha256(f.read_bytes()).hexdigest() != digest:
            bad.append(f"MODIFIED  {name}")
        else:
            ok.append(name)
    present = sorted(p.name for p in root.iterdir() if p.name in RUNTIME_ARTIFACTS)
    return ok, bad, present


def main() -> int:
    if not BASELINE.exists() or not (V1_ROOT / "main.py").exists():
        print("V1 files not found next to v2/ (is this the full repository?)"); return 2
    ok, bad, present = check()
    for n in ok:
        print(f"OK        {n}")
    for b in bad:
        print(b)
    if present:
        print(f"note: V1 run-time files present (created when V1 is run, expected): {', '.join(present)}")
    print(f"\n{len(ok)} of {len(ok) + len(bad)} V1 files identical to the recorded baseline.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
