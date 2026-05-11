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

Known limitation:
    `build_event_cli` runs validators only on labels that received a value.
    A missing label (`--ledger-url` not passed at all) silently skips its
    validator — even if you wired the strict `google_sheets_url` (vs
    `_or_empty`) validator. So `required` here means "must not be empty
    when present", not "must always be present". The receiving GAS catches
    truly-missing required fields (e.g. validateManagedLedger rejects empty
    Ledger URL for Capital Injection) — fix flows back to the operator as
    a FAILED row in the intake sheet rather than a clean CLI error.
    Tracked as future work; closing it would require adding
    `required_labels=` to build_event_cli.
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


def positive_integer(value: str) -> None:
    """Reject non-integer or non-positive (zero or negative) values."""
    raw = str(value).replace(",", "").strip()
    try:
        n = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"must be an integer (got {value!r})")
    if n <= 0:
        raise ValueError(f"must be > 0 (got {value!r})")


def latitude(value: str) -> None:
    """Decimal degrees in [-90, 90]. Empty allowed (some events log lat/lng optionally)."""
    raw = str(value or "").strip()
    if not raw:
        return
    try:
        n = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"latitude must be a number (got {value!r})")
    if not (-90 <= n <= 90):
        raise ValueError(f"latitude must be in [-90, 90] (got {n})")


def longitude(value: str) -> None:
    """Decimal degrees in [-180, 180]. Empty allowed."""
    raw = str(value or "").strip()
    if not raw:
        return
    try:
        n = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"longitude must be a number (got {value!r})")
    if not (-180 <= n <= 180):
        raise ValueError(f"longitude must be in [-180, 180] (got {n})")


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


_CURRENCY_START = re.compile(r"^[A-Za-z0-9]")
_CURRENCY_BAD = re.compile(r"[\x00-\x1f\x7f]")  # control chars only


def currency_code(value: str) -> None:
    """Accept a currency identifier string. Very loose by design — DAO
    currencies include fiat ISO codes ("USD", "BRL"), product SKUs with
    parens / commas / plus signs ("Cacao Almonds (KG)", "Amazon LFSEMINI ...
    + drawstring bag"), and equipment names. Just rejects empty, control
    chars, and inputs that don't start with a letter or digit."""
    raw = str(value).strip()
    if not raw:
        raise ValueError("currency cannot be empty")
    if not _CURRENCY_START.match(raw):
        raise ValueError(f"currency must start with a letter or digit (got {value!r})")
    if _CURRENCY_BAD.search(raw):
        raise ValueError(f"currency contains control characters (got {value!r})")


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


def google_sheets_url(value: str) -> None:
    """Required (non-empty) Google Sheets edit URL. Use for events that won't
    accept the offchain default (e.g. Capital Injection)."""
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Google Sheets URL is required")
    if "docs.google.com/spreadsheets/d/" not in raw:
        raise ValueError(
            f"must be a docs.google.com/spreadsheets/d/... URL (got {value!r})"
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
