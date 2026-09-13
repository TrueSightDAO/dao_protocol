#!/usr/bin/env python3
"""Real-time FX rate lookup - a self-serve exchange-rate primitive.

Agents and humans repeatedly hand-roll currency conversions when filing
``[CURRENCY CONVERSION EVENT]`` rows (e.g. computing the Implied Rate for a
USD to BRL transfer). Hand-rolling is exactly where stale (``Brazilian Reis``
was pinned at 0.2323 USD while the live rate had drifted ~18%) or mistyped
rates creep in.

This CLI fetches a LIVE (or historical) mid-market rate from a keyless public
source and prints it in the ``1 <src> = <rate> <tgt>`` shape that the
``truesight-dao-report-currency-conversion`` CLI auto-fills for
``--implied-rate``, so the value can be pasted straight in. The ``--compare-*``
options sanity-check an already hand-rolled conversion against the live rate.

Read-only: makes NO ledger writes and submits nothing to Edgar.

Sources (both keyless - no API key required):
    - open.er-api.com  live daily rates  (default, live mode)
    - frankfurter.dev  ECB reference rates; supports historical dates

Run from the dao_client repo root:

    python -m truesight_dao_client.modules.lookup_fx_rate --base USD --quote BRL
    python -m truesight_dao_client.modules.lookup_fx_rate --base USD --quote BRL --amount 1000
    python -m truesight_dao_client.modules.lookup_fx_rate --base USD --quote BRL --date 20260912
    # sanity-check a hand-rolled conversion: did 1000 USD really become 4985 BRL?
    python -m truesight_dao_client.modules.lookup_fx_rate --base USD --quote BRL \\
        --compare-source-amount 1000 --compare-target-amount 4985
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys

import requests

LIVE_URL = "https://open.er-api.com/v6/latest/{base}"
HIST_URL = "https://api.frankfurter.dev/v1/{date}"

DEFAULT_TIMEOUT = 20.0

# The rate the ledger's `Currencies` "Price in USD" column implies, for the two
# currencies the DAO books most often. Handy for the drift comparison. This is
# a HINT only - callers can pass any --ledger-price-in-usd.
LEDGER_USD_HINTS = {
    "BRL": 0.2323,  # 'Brazilian Reis' row observed 2026-09-13
    "USD": 1.0,
}


def _get_json(url: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """GET ``url`` and parse JSON. Split out so tests can monkeypatch it."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def _yyyymmdd_to_iso(value: str) -> str:
    return datetime.datetime.strptime(value.strip(), "%Y%m%d").strftime("%Y-%m-%d")


def fetch_rates(
    base: str, date: str | None = None, timeout: float = DEFAULT_TIMEOUT
) -> dict:
    """Return ``{"base", "date", "rates", "source"}`` for ``base``.

    ``date`` is a YYYYMMDD string (or ISO YYYY-MM-DD). ``None`` means live.
    """
    base = base.strip().upper()
    if date:
        iso = _yyyymmdd_to_iso(date) if date.isdigit() else date.strip()
        payload = _get_json(HIST_URL.format(date=iso), timeout=timeout)
        return {
            "base": payload.get("base", base).upper(),
            "date": payload.get("date", iso),
            "rates": payload.get("rates", {}),
            "source": "frankfurter.dev (ECB reference)",
        }
    payload = _get_json(LIVE_URL.format(base=base), timeout=timeout)
    if payload.get("result") not in (None, "success"):
        raise RuntimeError(payload.get("error-type", "rate lookup failed"))
    return {
        "base": payload.get("base_code", base).upper(),
        "date": (payload.get("time_last_update_utc", "") or "")[:16],
        "rates": payload.get("rates", {}),
        "source": "open.er-api.com (live daily)",
    }


def get_rate(
    base: str, quote: str, date: str | None = None, timeout: float = DEFAULT_TIMEOUT
) -> dict:
    """Resolve a single ``base -> quote`` rate. Adds ``quote`` and ``rate`` keys."""
    data = fetch_rates(base, date=date, timeout=timeout)
    quote = quote.strip().upper()
    rates = data.get("rates", {})
    if quote not in rates:
        raise KeyError(f"no rate for {quote} in {data.get('base')} feed")
    data["quote"] = quote
    data["rate"] = float(rates[quote])
    return data


def implied_rate_string(base: str, quote: str, rate: float) -> str:
    """Match the ``--implied-rate`` string the conversion CLI auto-fills."""
    return f"1 {base.strip().upper()} = {rate} {quote.strip().upper()}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Look up a live (or historical) FX rate. Read-only - does not "
            "submit any event to Edgar."
        ),
    )
    parser.add_argument(
        "--base", required=True, help="Base currency (e.g. USD, BRL, CNY)."
    )
    parser.add_argument(
        "--quote", required=True, help="Quote currency (e.g. BRL, USD)."
    )
    parser.add_argument(
        "--date",
        metavar="YYYYMMDD",
        help="Historical date (YYYYMMDD or YYYY-MM-DD). Omit for the live rate.",
    )
    parser.add_argument("--amount", type=float, help="Optional: convert this amount.")
    parser.add_argument(
        "--compare-source-amount",
        type=float,
        help="Optional: source amount of a hand-rolled conversion to sanity-check.",
    )
    parser.add_argument(
        "--compare-target-amount",
        type=float,
        help="Optional: target amount of a hand-rolled conversion to sanity-check.",
    )
    parser.add_argument(
        "--ledger-price-in-usd",
        type=float,
        help=(
            "Optional: a currency's stored 'Price in USD' from the Currencies tab, "
            "to report drift vs the live rate."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print raw JSON.")
    args = parser.parse_args(argv)

    try:
        data = get_rate(args.base, args.quote, date=args.date)
    except Exception as exc:  # noqa: BLE001 - surface any fetch/parse failure cleanly
        print(f"Rate lookup failed: {exc}", file=sys.stderr)
        return 1

    base, quote, rate = data["base"], data["quote"], data["rate"]
    if args.json:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    print(f"Source:   {data['source']}")
    print(f"As of:    {data['date']}")
    print(f"Rate:     {implied_rate_string(base, quote, rate)}")
    if args.amount is not None:
        print(
            f"Amount:   {args.amount:g} {base} = {round(args.amount * rate, 2):g} {quote}"
        )

    if args.compare_source_amount and args.compare_target_amount:
        hand = args.compare_target_amount / args.compare_source_amount
        drift = (hand - rate) / rate * 100 if rate else 0.0
        verdict = (
            "OK"
            if abs(drift) < 1.0
            else ("HAND-ROLLED RATE IS STALE" if drift < 0 else "OVER")
        )
        print(
            f"Compare:  hand-rolled 1 {base} = {round(hand, 6)} {quote} "
            f"vs live {rate} -> drift {drift:+.2f}% [{verdict}]"
        )

    ledger_hint = args.ledger_price_in_usd
    if ledger_hint is None:
        ledger_hint = LEDGER_USD_HINTS.get(quote) if base == "USD" else None
    if ledger_hint and base == "USD" and ledger_hint > 0:
        ledger_brl = 1.0 / ledger_hint
        dr = (ledger_brl - rate) / rate * 100
        print(
            f"Ledger:   Currencies '{quote}' = {ledger_hint} USD "
            f"(=> {round(ledger_brl, 4)} {quote}/USD) -> drift {dr:+.2f}% vs live"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
