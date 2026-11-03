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
    ddi_model_dir_override: Path | None = None    # MEDSAFE_DDI_MODEL_DIR
    ddi_metrics_dir_override: Path | None = None  # MEDSAFE_DDI_METRICS_DIR
    similar_use_min: float | None = None          # SIMILAR_USE_MIN: set only after the score distribution is reviewed

    @property
    def index_dir(self) -> Path:
        return self.artifacts_dir / "index"

    @property
    def ddi_model_dir(self) -> Path:
        return self.ddi_model_dir_override or self.artifacts_dir / "models" / "ddi_focal"

    @property
    def ddi_metrics_dir(self) -> Path:
        return self.ddi_metrics_dir_override or self.artifacts_dir / "metrics"

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
    ENCODER (or MEDSAFE_ENCODER), SIMILAR_USE_MIN, MEDSAFE_DDI_CLASSIFIER, MEDSAFE_DDI_MODEL_DIR, MEDSAFE_DDI_METRICS_DIR."""
    opt = lambda k: Path(os.environ[k]) if os.environ.get(k) else None
    return Settings(
        data_dir=Path(os.environ.get("MEDSAFE_DATA_DIR", REPO_ROOT / "data")),
        artifacts_dir=Path(os.environ.get("MEDSAFE_ARTIFACTS_DIR", AAKAASH_DIR / "artifacts")),
        trace_path=AAKAASH_DIR / "PAPER_TRACE.md",
        encoder_name=(os.environ.get("ENCODER") or os.environ.get("MEDSAFE_ENCODER") or "tfidf").strip().lower(),
        classifier_name=os.environ.get("MEDSAFE_DDI_CLASSIFIER", "focal"),
        ddi_model_dir_override=opt("MEDSAFE_DDI_MODEL_DIR"),
        ddi_metrics_dir_override=opt("MEDSAFE_DDI_METRICS_DIR"),
        similar_use_min=float(os.environ["SIMILAR_USE_MIN"]) if os.environ.get("SIMILAR_USE_MIN") else None,
    )
