# SOURCE: NOT IN PAPERS (own tooling). Installs the sbert index that notebooks/build_sbert_index.ipynb built on
# Kaggle. The output is generated data and is gitignored (aakaash/artifacts/index/). Never commit it.
"""Install sbert_index.zip into artifacts/index/sbert.

From the aakaash folder:
    .venv/Scripts/python.exe scripts/install_sbert.py C:/path/to/sbert_index.zip
    ... --force      # replace an sbert folder that already exists (including a partial one from a CPU build)
The zip must hold exactly vectors.npy, window_chunk.npy and manifest.json, and its manifest must carry the same
chunks_sha256 as artifacts/index/manifest.json. Otherwise nothing is written."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

AAKAASH = Path(__file__).resolve().parents[1]
EXPECTED = {"vectors.npy", "window_chunk.npy", "manifest.json"}


class InstallError(Exception):
    pass


def install(zip_path: Path, index_dir: Path, force: bool = False) -> dict:
    """Validate, then extract. Returns the sbert manifest. Raises InstallError and writes nothing on any problem."""
    zip_path, index_dir = Path(zip_path), Path(index_dir)
    if not zip_path.is_file():
        raise InstallError(f"{zip_path} does not exist.")
    top_file = index_dir / "manifest.json"
    if not top_file.is_file():
        raise InstallError(f"{top_file} is missing: build the chunks and TF-IDF index first (scripts/build_index.py).")
    top = json.loads(top_file.read_text(encoding="utf-8"))
    try:
        zf = zipfile.ZipFile(zip_path)
    except zipfile.BadZipFile as e:
        raise InstallError(f"{zip_path} is not a zip file ({e}).") from e
    with zf:
        names = set(zf.namelist())
        if names != EXPECTED:
            raise InstallError(f"The zip must hold exactly {sorted(EXPECTED)}; it holds {sorted(names)}.")
        m = json.loads(zf.read("manifest.json").decode("utf-8"))
        if m.get("encoder") != "sbert":
            raise InstallError(f"The zip's manifest is for encoder {m.get('encoder')!r}, not 'sbert'.")
        if m.get("chunks_sha256") != top.get("chunks_sha256"):
            raise InstallError(
                "chunks_sha256 does not match: the zip was built from different chunks "
                f"({str(m.get('chunks_sha256'))[:12]}...) than artifacts/index ({str(top.get('chunks_sha256'))[:12]}...). "
                "Nothing was installed. Never re-chunk (build_index.py --rechunk) after uploading chunks.jsonl to Kaggle.")
        if m.get("chunks") != top.get("chunks"):
            raise InstallError(f"Chunk count differs: zip {m.get('chunks')}, index {top.get('chunks')}.")
        target = index_dir / "sbert"
        if target.exists() and not force:
            raise InstallError(f"{target} already exists. Pass --force to replace it.")
        tmp = index_dir / "sbert.installing"
        if tmp.exists():
            shutil.rmtree(tmp)
        tmp.mkdir()
        try:
            for name in sorted(EXPECTED):
                with zf.open(name) as src, open(tmp / name, "wb") as dst:
                    shutil.copyfileobj(src, dst)
            if target.exists():
                shutil.rmtree(target)
            tmp.rename(target)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return m


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("zip", type=Path, help="path to sbert_index.zip downloaded from Kaggle")
    ap.add_argument("--index-dir", type=Path, default=AAKAASH / "artifacts" / "index")
    ap.add_argument("--force", action="store_true", help="replace an existing sbert folder")
    a = ap.parse_args()
    try:
        m = install(a.zip, a.index_dir, a.force)
    except InstallError as e:
        sys.exit(f"REFUSED: {e}")
    size = sum(f.stat().st_size for f in (a.index_dir / "sbert").iterdir())
    print(f"installed {a.index_dir / 'sbert'}")
    print(f"  model {m.get('model')} revision {m.get('model_revision')}, device {m.get('device')} ({m.get('gpu')})")
    print(f"  {m['chunks']} chunks -> {m['windows']} windows x {m['dimension']} dimensions, {size / 1e6:.1f} MB, "
          f"built in {m.get('seconds')} s")
    print("  chunks_sha256 matches artifacts/index/manifest.json")
    print("To use it: set ENCODER=sbert and restart the API. TF-IDF stays the default until you switch.")


if __name__ == "__main__":
    main()
