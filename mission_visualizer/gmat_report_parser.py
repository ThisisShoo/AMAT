from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

import pandas as pd

_GREG_RE = re.compile(r"^\s*(\d{2}\s+\w{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+(.*)$")


def _clean_header(line: str) -> list[str]:
    return [c.strip() for c in next(csv.reader([line])) if c.strip()]


def _coerce(value: str) -> Any:
    v = value.strip()
    if v == "":
        return None
    try:
        return float(v)
    except ValueError:
        return v


def parse_gmat_report(path: str | Path) -> pd.DataFrame:
    """Parse GMAT ReportFile output.

    GMAT sometimes writes comma-separated headers with comma-separated data rows, and sometimes
    writes comma-separated headers with fixed-width / whitespace data rows. This parser handles
    both so downstream visualization does not depend on GMAT formatting preferences.
    """
    path = Path(path)
    raw_lines = [ln.rstrip("\n") for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    if not raw_lines:
        return pd.DataFrame()

    header = _clean_header(raw_lines[0])
    rows: list[dict[str, Any]] = []
    for line in raw_lines[1:]:
        if not line.strip():
            continue
        # Preferred case: comma-separated row.
        if "," in line:
            parts = [p.strip() for p in next(csv.reader([line]))]
        else:
            # GMAT sparse/fixed-width style. Preserve Gregorian timestamp as one field.
            m = _GREG_RE.match(line)
            if m:
                parts = [m.group(1)] + m.group(2).split()
            else:
                parts = line.split()

        if len(parts) < len(header):
            parts = parts + [""] * (len(header) - len(parts))
        if len(parts) > len(header):
            # Keep parser resilient; extra fields are preserved for diagnostics.
            header_ext = header + [f"__extra_{i}" for i in range(len(parts) - len(header))]
        else:
            header_ext = header
        rows.append({col: _coerce(parts[i]) for i, col in enumerate(header_ext)})

    df = pd.DataFrame(rows)
    # Drop totally empty columns created by GMAT spacing quirks.
    df = df.dropna(axis=1, how="all")
    return df


def resolve_column(columns: list[str], desired: str | None, suffixes: list[str] | None = None) -> str | None:
    """Resolve a manifest hint to an actual DataFrame column.

    Tries exact match, then case-insensitive exact match, then suffix match. Useful when manifest
    says X/Y/Z but GMAT produced Object.Frame.X.
    """
    if not columns:
        return None
    candidates: list[str] = []
    if desired:
        candidates.append(desired)
    if suffixes:
        candidates.extend(suffixes)

    for cand in candidates:
        if cand in columns:
            return cand
    lowered = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand and cand.lower() in lowered:
            return lowered[cand.lower()]
    for cand in candidates:
        if not cand:
            continue
        suffix = cand if cand.startswith(".") else "." + cand
        matches = [c for c in columns if c.endswith(suffix) or c == cand]
        if matches:
            return matches[0]
    return None


def resolve_time_column(columns: list[str], hints: list[str] | None = None) -> str | None:
    hints = hints or []
    # Prefer numeric time bases for interpolation even when the manifest lists UTC first.
    preferred_suffixes = ["ElapsedSecs", "A1ModJulian", "UTCModJulian", "TAIModJulian", "UTCGregorian"]
    expanded: list[str] = []
    for suffix in preferred_suffixes:
        expanded.extend([h for h in hints if h == suffix or h.endswith("." + suffix)])
        expanded.append(suffix)
    for hint in expanded:
        col = resolve_column(columns, hint, [hint])
        if col:
            return col
    for suffix in (".ElapsedSecs", ".A1ModJulian", ".UTCModJulian", ".TAIModJulian", ".UTCGregorian"):
        for c in columns:
            if c.endswith(suffix):
                return c
    return None


def infer_object_frame_from_columns(columns: list[str]) -> tuple[str | None, str | None]:
    for c in columns:
        parts = c.split(".")
        if len(parts) >= 3 and parts[-1] in {"X", "Y", "Z", "VX", "VY", "VZ"}:
            return parts[0], parts[-2]
    return None, None
