# SOURCE: NOT IN PAPERS. Parses aakaash/PAPER_TRACE.md as it is; categories come from the text
# of the source cell and are never inferred. A row that does not start with a known label is
# "unclassified" and a row with the wrong number of cells is reported, not dropped.
"""Parse PAPER_TRACE.md into rows."""
from __future__ import annotations

import re
from collections import Counter

from ..config import Settings
from ..schemas import TraceResponse, TraceRow

_SPLIT = re.compile(r"(?<!\\)\|")
_EXPECTED = ["component", "file", "source", "note", "status"]


def _cells(line: str) -> list[str]:
    return [c.strip().replace("\\|", "|") for c in _SPLIT.split(line.strip().strip("|"))]


def _category(source: str) -> str:
    s = source.strip().upper()
    if s.startswith("FROM BASELINE REVIEW"):
        return "from_baseline_review"
    if s.startswith("FROM PAPERS"):
        return "from_papers"
    if s.startswith("NOT IN PAPERS"):
        return "not_in_papers"
    return "unclassified"


def _status_kind(status: str | None) -> str:
    s = (status or "").strip().upper()
    for kind in ("UNTESTED", "RAN", "VERIFIED"):
        if s.startswith(kind):
            return kind.lower()
    return "unknown"


def parse_trace(text: str) -> tuple[list[TraceRow], list[str], list[str]]:
    rows: list[TraceRow] = []
    malformed: list[str] = []
    preamble: list[str] = []
    header: list[str] | None = None
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            if line.strip() and not line.startswith("#"):
                preamble.append(line.strip())
            continue
        cells = _cells(line)
        if header is None:
            header = [c.lower() for c in cells]
            if header != _EXPECTED:
                malformed.append(line)
                header = None
            continue
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if len(cells) != len(header):
            malformed.append(line)
            continue
        d = dict(zip(header, cells))
        status = d.get("status")
        rows.append(TraceRow(
            component=d["component"], file=d["file"], source=d["source"], note=d["note"],
            status=status, category=_category(d["source"]), status_kind=_status_kind(status)))
    return rows, malformed, preamble


def get_trace(settings: Settings) -> TraceResponse:
    path = settings.trace_path
    if not path.is_file():
        return TraceResponse(status="not_ready", reason=f"{settings.display(path)} does not exist.",
                             fix="Restore aakaash/PAPER_TRACE.md.")
    rows, malformed, preamble = parse_trace(path.read_text(encoding="utf-8"))
    return TraceResponse(
        status="ready", rows=rows, malformed_rows=malformed, preamble=preamble,
        counts_by_category=dict(Counter(r.category for r in rows)),
        counts_by_status=dict(Counter(r.status_kind for r in rows)))
