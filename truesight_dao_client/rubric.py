"""TrueSight DAO — TDG issuance rubric (single source of truth).

TDG is DERIVED from a contribution's Type + Amount; it is never supplied by the
caller. Keep this in lockstep with the dapp formula (report_contribution.html)
and, later, with the npm @truesight_dao/dao-client package.

Rubric (Intiatives Scoring Rubric):
  - Time (Minutes): TDG = hours * 100  == minutes / 60 * 100
  - USD:            TDG = USD amount    (1:1)
  - USDT received / USDT sent:  1:1
"""
from __future__ import annotations

TDG_PER_HOUR = 100.0

_ONE_TO_ONE_TYPES = {"USD", "USDT received", "USDT sent"}

_TIME_TYPES = {"Time (Minutes)", "Time"}


def parse_amount(raw) -> float:
    """Tolerant numeric parse for the Amount field (strip $, commas, whitespace)."""
    if raw is None:
        raise ValueError("Amount is required to compute TDG")
    s = str(raw).strip().lstrip("$").replace(",", "")
    try:
        return float(s)
    except ValueError:
        raise ValueError(f"Amount must be numeric to compute TDG, got {raw!r}")


def tdg_for(contribution_type: str, amount) -> float:
    """Authoritative TDG for a contribution.

    `amount` is minutes for Time types, currency units for USD/USDT types.
    Returns a float rounded to 2 decimals. Raises ValueError on an unknown type.
    """
    t = (contribution_type or "").strip()
    value = parse_amount(amount)
    if t in _TIME_TYPES:
        return round(value / 60.0 * TDG_PER_HOUR, 2)
    if t in _ONE_TO_ONE_TYPES:
        return round(value, 2)
    raise ValueError(
        f"No TDG rubric for contribution Type {contribution_type!r}. "
        f"Known: Time (Minutes), USD, USDT received, USDT sent."
    )


def format_tdg(value: float) -> str:
    """Canonical string form used in the signed payload (2dp, matches the dapp)."""
    return f"{value:.2f}"


def amount_and_tdg_from_time(hours: float | None = 0, minutes: float | None = 0) -> tuple[str, str]:
    """Helper for the hours/minutes entry path (report_ai_agent_contribution).

    Returns (amount_string_in_minutes, tdg_string).
    """
    total_minutes = int((hours or 0) * 60 + (minutes or 0))
    return str(total_minutes), format_tdg(tdg_for("Time (Minutes)", total_minutes))
