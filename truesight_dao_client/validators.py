"""Reusable per-attribute validators + normalizers for `build_event_cli`.

`build_event_cli(validators=..., normalizers=...)` already supports per-label
hooks — they just weren't being used. This module gives event modules a small
shared toolkit so the same checks (positive numbers, YYYYMMDD dates, currency
codes, URLs) don't get re-inlined everywhere.

Convention:
- A **validator** raises `ValueError(message)` if the value is invalid; otherwise returns `None`.
  `build_event_cli` catches the ValueError and exits with `parser.error(str(exc))`.
- A **normalizer** receives a string and returns a (cleaned) string. Runs after
  validation, so `currency_code` will see "usd" as valid (validator) AND
  return "USD" (normalizer).

Use as:

    from ..validators import (
        positive_number, yyyymmdd_date, currency_code,
        normalize_currency, normalize_date_to_yyyymmdd,
    )

    main = build_event_cli(
        event_name='CURRENCY CONVERSION EVENT',
        canonical_labels=[...],
        validators={
            'Source Amount': positive_number,
            'Source Currency': currency_code,
            ...
        },
        normalizers={
            'Source Currency': normalize_currency,
            'Conversion Date': normalize_date_to_yyyymmdd,
        },
    )
"""
from __future__ import annotations

import datetime
import re


# ---------------------------------------------------------------------------
# Validators (raise ValueError on invalid; return None on valid)
# ---------------------------------------------------------------------------

def required(value: str) -> None:
    """Reject empty / whitespace-only values."""
    if value is None or not str(value).strip():
        raise ValueError("required field cannot be empty")


def positive_number(value: str) -> None:
    """Reject non-numeric, NaN, or non-positive values. Accepts comma thousands separators."""
    raw = str(value).replace(",", "").strip()
    try:
        n = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"must be a number (got {value!r})")
    if not (n > 0):
        raise ValueError(f"must be > 0 (got {value!r})")


def non_negative_integer(value: str) -> None:
    raw = str(value).replace(",", "").strip()
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"must be an integer (got {value!r})")
    if n < 0:
        raise ValueError(f"must be >= 0 (got {value!r})")


_YYYYMMDD = re.compile(r"^\d{8}$")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def yyyymmdd_date(value: str) -> None:
    """Accepts YYYYMMDD or ISO YYYY-MM-DD; rejects anything else.

    Pair with `normalize_date_to_yyyymmdd` to canonicalize ISO → YYYYMMDD before send.
    """
    raw = str(value).strip()
    if _YYYYMMDD.match(raw):
        try:
            datetime.datetime.strptime(raw, "%Y%m%d")
        except ValueError as exc:
            raise ValueError(f"YYYYMMDD value {value!r} is not a real calendar date: {exc}")
        return
    if _ISO_DATE.match(raw):
        try:
            datetime.datetime.strptime(raw, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"ISO date {value!r} is not a real calendar date: {exc}")
        return
    raise ValueError(f"must be YYYYMMDD or YYYY-MM-DD (got {value!r})")


_CURRENCY_CODE = re.compile(r"^[A-Za-z][A-Za-z0-9 .'\-]{0,49}$")


def currency_code(value: str) -> None:
    """Accept a currency identifier string. Loose by design — DAO currencies
    include fiat ISO codes ("USD", "BRL"), product SKUs ("Cacao Almonds (KG)"),
    and equipment names. Just rejects empty / nonsense, not non-ISO."""
    raw = str(value).strip()
    if not raw:
        raise ValueError("currency cannot be empty")
    if not _CURRENCY_CODE.match(raw):
        raise ValueError(
            f"currency {value!r} contains unexpected characters; "
            "use letters/digits/space/.'- and start with a letter"
        )


_URL = re.compile(r"^https?://", re.IGNORECASE)


def url_or_empty(value: str) -> None:
    """Empty is fine (e.g. offchain ledger URL); otherwise must look like http(s)://..."""
    raw = str(value).strip()
    if not raw:
        return
    if not _URL.match(raw):
        raise ValueError(f"must be empty or a http(s) URL (got {value!r})")


def google_sheets_url_or_empty(value: str) -> None:
    """Stricter than `url_or_empty`: must be a Google Sheets edit URL or empty."""
    raw = str(value).strip()
    if not raw:
        return
    if "docs.google.com/spreadsheets/d/" not in raw:
        raise ValueError(
            f"must be empty or a docs.google.com/spreadsheets/d/... URL (got {value!r})"
        )


# ---------------------------------------------------------------------------
# Normalizers (return cleaned string)
# ---------------------------------------------------------------------------

def normalize_currency(value: str) -> str:
    """Strip + uppercase ISO-like currency codes; leave longer descriptive names alone.

    "usd" -> "USD"; "brl " -> "BRL"; "Brazilian Reis" -> "Brazilian Reis"
    (we don't uppercase multi-word names because the DAO catalog uses Title Case for SKU-style currencies)."""
    s = str(value or "").strip()
    if not s:
        return s
    return s.upper() if (len(s) <= 5 and s.isalpha()) else s


def normalize_number(value: str) -> str:
    """Strip whitespace + commas. Keeps the decimal as-is so the GAS parses it cleanly."""
    return str(value or "").strip().replace(",", "")


def normalize_date_to_yyyymmdd(value: str) -> str:
    """ISO YYYY-MM-DD → YYYYMMDD. Already-YYYYMMDD pass through."""
    raw = str(value or "").strip()
    if _ISO_DATE.match(raw):
        return raw.replace("-", "")
    return raw


def strip(value: str) -> str:
    return str(value or "").strip()
