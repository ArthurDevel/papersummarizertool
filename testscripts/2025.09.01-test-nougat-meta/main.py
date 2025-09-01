#!/usr/bin/env python3
"""
Scan the repo's data/ directory for PDFs and convert each to Markdown (.mmd)
using Meta's Nougat, saving the output next to the source PDF.

Install nougat in your venv first:
  source .venv/bin/activate && pip install "nougat-ocr[api]"

Reference: https://github.com/facebookresearch/nougat
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DATA_SUBDIR = "testscripts/data"


def main() -> int:
    # testscripts/<date>/main.py → repo root is parents[2]
    project_root = Path(__file__).resolve().parents[2]
    data_dir = project_root / DATA_SUBDIR

    if not data_dir.exists():
        sys.stderr.write(f"[error] Data directory not found: {data_dir}\n")
        return 1

    pdf_paths = sorted(p for p in data_dir.rglob("*.pdf") if p.is_file())
    if not pdf_paths:
        print(f"No PDFs found under {data_dir}")
        return 0

    print(f"Found {len(pdf_paths)} PDF(s) under {data_dir}")
    for pdf_path in pdf_paths:
        out_dir = pdf_path.parent
        cmd = [
            "nougat",
            str(pdf_path),
            "-o",
            str(out_dir),
        ]
        print("$", " ".join(cmd))
        # If conversion fails, let it crash (raise CalledProcessError)
        subprocess.run(cmd, check=True)

    print("Done. Outputs saved next to each PDF.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


