from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable


class EpochFormatError(ValueError):
    """Raised when an epoch cannot be normalized or rendered."""


def _parse_epoch(value: str) -> datetime:
    text = str(value).strip()
    if not text:
        raise EpochFormatError("epoch must not be empty")

    # AMAT canonical form and common ISO-8601 variants.
    iso = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            # Mission inputs historically omitted offsets. Treat them as UTC,
            # then write the explicit canonical Z suffix.
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    # Migration support for GMAT UTCGregorian inputs.
    for fmt in ("%d %b %Y %H:%M:%S.%f", "%d %b %Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise EpochFormatError(
        f"Unsupported epoch {value!r}; use UTC ISO-8601 such as "
        "2026-01-01T00:00:00.000Z"
    )


def canonicalize_epoch(value: str) -> str:
    """Return AMAT's backend-neutral UTC ISO-8601 representation.

    Millisecond precision is used in persisted JSON because it is accepted by
    the initial backend set and matches GMAT's practical script precision.
    """
    dt = _parse_epoch(value)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _format_gmat(value: str) -> str:
    dt = _parse_epoch(value)
    # GMAT UTCGregorian: 01 Jan 2026 00:00:00.000
    return dt.strftime("%d %b %Y %H:%M:%S.%f")[:-3]


def _format_iso(value: str) -> str:
    return canonicalize_epoch(value)


_BACKEND_FORMATTERS: dict[str, Callable[[str], str]] = {
    "gmat": _format_gmat,
    "orekit": _format_iso,
    "stk": _format_iso,
    "tudat": _format_iso,
    "spice": _format_iso,
}


def register_epoch_formatter(backend: str, formatter: Callable[[str], str]) -> None:
    """Register a backend renderer without changing the canonical model."""
    key = backend.strip().lower()
    if not key:
        raise EpochFormatError("backend name must not be empty")
    _BACKEND_FORMATTERS[key] = formatter


def format_epoch_for_backend(value: str, backend: str) -> str:
    key = backend.strip().lower()
    try:
        formatter = _BACKEND_FORMATTERS[key]
    except KeyError as exc:
        raise EpochFormatError(f"No epoch formatter registered for backend {backend!r}") from exc
    return formatter(value)
