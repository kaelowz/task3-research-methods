"""Losslessly convert the original survey CSV to JSON Lines (data/raw/test_run.jsonl).

Original data: Nawaz, S. (2026) Mendeley Data, DOI 10.17632/srd3wmjd4r.1 (CC BY 4.0).
The CSV is kept untouched in data/raw/ for provenance; the pipeline reads the JSONL.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def main(src: str = "data/raw/Data_cleaned.csv", dst: str = "data/raw/test_run.jsonl") -> None:
    df = pd.read_csv(src, encoding="utf-8-sig")
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "w", encoding="utf-8") as fh:
        for rec in df.to_dict(orient="records"):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Converted {len(df)} records x {df.shape[1]} columns -> {dst}")


if __name__ == "__main__":
    main()
