# SOURCE: NOT IN PAPERS (own tooling). Packs the files the hosted backend reads at run time.
"""Makes hosting_bundle.tar.gz: the runtime data for the Render deployment (see ../render.yaml and Dockerfile).

Upload the tarball somewhere with a direct-download link (for example a GitHub Release asset) and give that
link to the Docker build as DATA_URL. The tarball unpacks into the repo root, so paths are data/... and
aakaash/artifacts/...  It never contains .env, app.db, keys, screenshots, training corpora or the 1.8 GB DailyMed zip.

Default (fits Render free, 512 MB): TF-IDF label index, catalogue, names, metrics, appms and DDI corpus files.
  --with-sbert   adds the sbert vectors (193 MB on disk, mmap'd) -- needs torch at run time, does not fit 512 MB
  --with-model   adds the Focal Loss classifier (421 MB) -- needs torch, does not fit 512 MB

Run from aakaash/:  ..\.venv\Scripts\python.exe scripts\build_hosting_bundle.py   (or aakaash\.venv\...)"""
from __future__ import annotations

import argparse
import sys
import tarfile
from pathlib import Path

AAKAASH = Path(__file__).resolve().parents[1]
REPO = AAKAASH.parent

BASE = [  # (path relative to repo root, skip predicate or None)
    "aakaash/artifacts/catalogue.json",
    "aakaash/artifacts/names.json",
    "aakaash/artifacts/dailymed_stats.json",
    "aakaash/artifacts/metrics",
    "aakaash/artifacts/index",
    "data/appms",
    "data/ddi2013/DDICorpus",
]
NEVER = {".env", "app.db", ".DS_Store"}


def wanted(rel: str, with_sbert: bool) -> bool:
    parts = rel.split("/")
    if parts[-1] in NEVER or parts[-1].startswith(".env"):
        return False
    if not with_sbert and "aakaash/artifacts/index/sbert" in rel:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(REPO / "hosting_bundle.tar.gz"))
    ap.add_argument("--with-sbert", action="store_true")
    ap.add_argument("--with-model", action="store_true")
    a = ap.parse_args()
    items = list(BASE) + (["aakaash/artifacts/models"] if a.with_model else [])
    out = Path(a.out)
    n = size = 0
    with tarfile.open(out, "w:gz", compresslevel=6) as tar:
        for item in items:
            root = REPO / item
            if not root.exists():
                print(f"MISSING {item}", file=sys.stderr)
                return 1
            for f in sorted([root] if root.is_file() else root.rglob("*")):
                if not f.is_file():
                    continue
                rel = f.relative_to(REPO).as_posix()
                if not wanted(rel, a.with_sbert):
                    continue
                tar.add(f, arcname=rel)
                n += 1
                size += f.stat().st_size
    print(f"{out}: {n} files, {size / 1048576:.0f} MB unpacked, {out.stat().st_size / 1048576:.0f} MB packed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
