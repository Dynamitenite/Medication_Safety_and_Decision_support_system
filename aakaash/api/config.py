# SOURCE: NOT IN PAPERS. Own configuration. Paths follow aakaash/CLAUDE.md (data/ at the repo
# root, gitignored; generated files under aakaash/artifacts/, gitignored).
"""Settings, read from the environment on every call so tests and users can override them."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

AAKAASH_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = AAKAASH_DIR.parent


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    artifacts_dir: Path
    trace_path: Path
    encoder_name: str
    classifier_name: str

    def _roots(self) -> list[tuple[Path, str]]:
        """Known absolute locations and the repo-relative name shown instead, longest first."""
        roots = [(self.trace_path, "aakaash/PAPER_TRACE.md"),
                 (self.artifacts_dir, "aakaash/artifacts"),
                 (self.data_dir, "data"),
                 (REPO_ROOT, "")]
        return sorted(roots, key=lambda r: len(str(r[0])), reverse=True)

    def display(self, path: Path) -> str:
        """Repo-relative form of a path (data/tac2017). Absolute paths never leave the server."""
        for root, shown in self._roots():
            try:
                rel = Path(path).relative_to(root).as_posix()
            except ValueError:
                continue
            return "/".join(p for p in (shown, "" if rel == "." else rel) if p)
        return Path(path).name

    def scrub(self, text: str) -> str:
        """Replace absolute paths inside free text (for example exception messages)."""
        for root, shown in self._roots():
            for form in {str(root), root.as_posix(), str(root).replace("\\", "\\\\")}:
                text = text.replace(form, shown or ".")
        return re.sub(r"[A-Za-z]:[\\/][^\s'\"]*", "<path>", text)


def get_settings() -> Settings:
    """FastAPI dependency. Override with MEDSAFE_DATA_DIR, MEDSAFE_ARTIFACTS_DIR,
    MEDSAFE_ENCODER, MEDSAFE_DDI_CLASSIFIER."""
    return Settings(
        data_dir=Path(os.environ.get("MEDSAFE_DATA_DIR", REPO_ROOT / "data")),
        artifacts_dir=Path(os.environ.get("MEDSAFE_ARTIFACTS_DIR", AAKAASH_DIR / "artifacts")),
        trace_path=AAKAASH_DIR / "PAPER_TRACE.md",
        encoder_name=os.environ.get("MEDSAFE_ENCODER", "tfidf"),
        classifier_name=os.environ.get("MEDSAFE_DDI_CLASSIFIER", "linear_baseline"),
    )
