# dao_client — TDG Rubric Hardening (make the client compute TDG, not the caller)

**Author:** Claude Anthropic (Opus 4.8) — 2026-07-02
**Repo:** `TrueSightDAO/dao_protocol` — specifically the **Python client `truesight_dao_client/`** (the CLI LLMs invoke). This same repo also contains the npm package `packages/dao-client/`, but this PR does **not** touch it — hardening the npm/dapp side onto one shared rubric is a "later" follow-up (§ Appendix).
**Goal:** Make it **impossible for an LLM (or any caller) to submit a wrong TDG** via dao_client. TDG becomes a value the client *computes* from `Type` + `Amount` using a single rubric, never a value the caller supplies. When `--tdg-issued` is passed and disagrees, **ignore it and warn** (Gary's decision: option (a)).

This doc is self-contained and paste-ready. Build it in ONE PR.

---

## 1. Why (root cause, confirmed)

The TDG formula already exists in two places — the **dapp** (browser JS) and **`report_ai_agent_contribution.py`** (`_compute_amount_and_tdg`, *"matching the DApp formula"*). But the generic path LLMs reach for, **`truesight-dao-report-contribution`**, does **not** compute — it stamps whatever `--tdg-issued` the caller passes, verbatim. So an LLM that fat-fingers `--tdg-issued 750` for 45 minutes signs and submits `750`. That's the "stupid submissions."

**Fix:** one shared rubric module; the generic contribution CLI computes TDG from the signed inputs; `--tdg-issued` is demoted to an ignored-with-warning override. After this, the only TDG-emitting client paths (`report_contribution`, `report_ai_agent_contribution`) both derive TDG from the rubric — the caller cannot inject a wrong number.

---

## 2. Pre-flight — exact current state (captured so no execution turn re-discovers; §5d)

**The single dumb path** — `truesight_dao_client/modules/report_contribution.py` (whole file is 67 lines). It builds its CLI from the factory:
```python
main = build_event_cli(
    event_name='CONTRIBUTION EVENT',
    canonical_labels=['Type', 'Amount', 'Description', 'Contributor(s)', 'TDG Issued', 'Attached Filename', 'Destination Contribution File Location'],
    dapp_page='report_contribution.html',
    validators={'Type': _validate_contribution_type, 'Contributor(s)': dao_contributor_name},
    normalizers={'Contributor(s)': lambda v: strip_email_addresses(_normalize_contributors(v))},
)
```
`'TDG Issued'` is a canonical label → the factory auto-exposes `--tdg-issued` and collects its raw value. `VALID_CONTRIBUTION_TYPES = {"Time (Minutes)", "USD", "USDT sent", "USDT received"}` is already defined + validated in this file.

**The factory** — `truesight_dao_client/edgar_client.py`, `build_event_cli(...)` (lines 307–469). It: adds one `--flag` per canonical label (`label_to_flag`, line 328), collects `attrs`, applies `validators` then `normalizers` into `normalized_attrs` (loop ends **line 414**), then does attachment auto-fill and `client.sign/submit`. **There is no computation/derivation hook.** The clean injection point is **immediately after the normalizers loop (after line 414), before `client = EdgarClient.from_env()` (line 416).**

**The reference formula** — `truesight_dao_client/modules/report_ai_agent_contribution.py`:
```python
def _compute_amount_and_tdg(contribution_type, hours, minutes, usd):
    # Time: Amount = total minutes (h*60+m); TDG = total_hours * 100, round 2dp
    # USD:  Amount = USD value;             TDG = USD value
    if contribution_type == "Time":
        total_minutes = int((hours or 0) * 60 + (minutes or 0))
        total_hours = (hours or 0) + (minutes or 0)/60.0
        return str(total_minutes), f"{round(total_hours*100, 2):.2f}"
    else:  # USD
        val = usd or 0
        return f"{val:.2f}", f"{val:.2f}"
```
Its `main()` maps the public type to an internal one: `_type_map = {"Time (Minutes)": "Time", ...}` (line 173), `internal_type = _type_map.get(args.type, "Time")` (line 178). This module has **no `--tdg-issued` flag** — it already computes, so it is *not* a leak. We only refactor it to share the rubric (SSOT).

**Other modules do NOT emit TDG.** `grep -rn "TDG Issued\|tdg_issued" truesight_dao_client/modules/` returns only `report_contribution.py` and `report_ai_agent_contribution.py`. `report_capital_injection`, `report_dao_expenses`, `report_sales`, `report_asset_receipt` do not set a TDG in the client payload (their TDG, if any, is scored downstream). **So only `report_contribution.py` needs the derive hook.**

**Package layout:** modules live in `truesight_dao_client/`; siblings include `validators.py` (put the new `rubric.py` here). Tests are pytest under `tests/` (e.g. `tests/test_dao_signature.py`).

**Rubric constants (from the dapp / AI-agent formula):** `TDG = 100 per hour`; USD `1:1`. Rounding: **2 decimals**, formatted `"{:.2f}"`.

✅ **Pre-flight Completeness (§5d):** every file, line anchor, formula, and injection point this PR touches is captured above. No execution turn needs to read another file to build it.

---

## 3. Change set (ONE PR)

### 3.1 NEW file — `truesight_dao_client/rubric.py` (single source of truth)

```python
"""TrueSight DAO — TDG issuance rubric (single source of truth).

TDG is DERIVED from a contribution's Type + Amount; it is never supplied by the
caller. Keep this in lockstep with the dapp formula (report_contribution.html)
and, later, with the npm @truesight_dao/dao-client package.

Rubric (Intiatives Scoring Rubric):
  - Time (Minutes): TDG = hours * 100  == minutes / 60 * 100
  - USD:            TDG = USD amount    (1:1)
  - USDT received / USDT sent:  1:1  (see OPEN DECISION in the impl plan — confirm)
"""
from __future__ import annotations

TDG_PER_HOUR = 100.0

# Types whose TDG equals the reported amount 1:1.
_ONE_TO_ONE_TYPES = {"USD", "USDT received", "USDT sent"}

# Public canonical type -> normalized key (accept both public and internal spellings).
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
```

> **OPEN DECISION (confirm with Gary before final merge):** the TDG rubric for **`USDT received`** and **`USDT sent`**. Defaulted to **1:1** above (same as USD). If sending USDT should *not* issue positive TDG (or uses a different factor), adjust `_ONE_TO_ONE_TYPES` / add an explicit branch. Time + USD are certain; USDT is the only unknown.

### 3.2 `truesight_dao_client/edgar_client.py` — add a `derive` hook to `build_event_cli`

Add the parameter to the signature (after `required_labels`):
```python
def build_event_cli(
    *,
    event_name: str,
    canonical_labels: list[str] | None = None,
    dapp_page: str | None = None,
    validators: dict[str, callable] | None = None,
    normalizers: dict[str, callable] | None = None,
    defaults: dict[str, str] | None = None,
    required_labels: list[str] | None = None,
    derive: callable | None = None,   # <-- NEW: (attrs:list[(lbl,val)]) -> attrs; may raise ValueError
):
```
Document it in the docstring (one line): *"`derive` runs after normalizers and may recompute/override attributes (e.g. authoritative TDG). Raise ValueError for a friendly CLI error."*

Then, **immediately after the normalizers loop that builds `normalized_attrs` (right after line 414), before `client = EdgarClient.from_env()`**, insert:
```python
        # Server/rubric-authoritative overrides (e.g. computed TDG). Runs on the
        # signed inputs so the caller cannot inject a wrong derived value.
        if derive is not None:
            try:
                normalized_attrs = derive(normalized_attrs)
            except ValueError as exc:
                parser.error(str(exc))
```
No other change to the factory. (The override happens *before* signing, so the computed TDG is what gets signed + submitted — consistent, not a post-hoc ledger patch.)

### 3.3 `truesight_dao_client/modules/report_contribution.py` — compute TDG, demote `--tdg-issued`

Add imports + a derive function, and pass `derive=` + `required_labels=` into the factory:
```python
import sys
from ..rubric import tdg_for, format_tdg

def _authoritative_tdg(attrs):
    """Recompute 'TDG Issued' from Type + Amount. Ignore (and warn about) any
    caller-supplied --tdg-issued that disagrees. TDG is computed, never supplied."""
    d = dict(attrs)
    ctype = d.get("Type")
    amount = d.get("Amount")
    if ctype is None or amount is None:
        # required_labels guarantees these for CONTRIBUTION EVENT; guard anyway.
        return attrs
    computed = format_tdg(tdg_for(ctype, amount))   # may raise ValueError -> parser.error
    supplied = d.get("TDG Issued")
    if supplied is not None and str(supplied).strip() != computed:
        print(
            f"[report-contribution] --tdg-issued {supplied!r} IGNORED; using rubric value "
            f"{computed} (Type={ctype!r}, Amount={amount!r}). TDG is computed, not client-supplied.",
            file=sys.stderr,
        )
    # Emit the authoritative TDG (replace in place, or insert after Contributor(s)).
    out, replaced = [], False
    for lbl, val in attrs:
        if lbl == "TDG Issued":
            out.append((lbl, computed)); replaced = True
        else:
            out.append((lbl, val))
    if not replaced:
        idx = next((i for i, (l, _) in enumerate(out) if l == "Contributor(s)"), len(out) - 1)
        out.insert(idx + 1, ("TDG Issued", computed))
    return out


main = build_event_cli(
    event_name='CONTRIBUTION EVENT',
    canonical_labels=['Type', 'Amount', 'Description', 'Contributor(s)', 'TDG Issued', 'Attached Filename', 'Destination Contribution File Location'],
    dapp_page='report_contribution.html',
    required_labels=['Type', 'Amount', 'Contributor(s)'],   # <-- NEW: Amount needed to compute TDG
    validators={'Type': _validate_contribution_type, 'Contributor(s)': dao_contributor_name},
    normalizers={'Contributor(s)': lambda v: strip_email_addresses(_normalize_contributors(v))},
    derive=_authoritative_tdg,                               # <-- NEW
)
```
Update the module docstring to note: *"TDG Issued is computed from Type + Amount; `--tdg-issued` is accepted for backward-compat but ignored (a warning is printed if it disagrees)."*

> Behavior change to call out in the PR: `Amount` is now **required** (previously a contribution could be submitted without it). This is intentional — TDG can't be computed without it. `--tdg-issued` still parses (no breakage for existing scripts) but no longer affects the payload.

### 3.4 `truesight_dao_client/modules/report_ai_agent_contribution.py` — delegate to the rubric (SSOT, no behavior change)

Replace the body of `_compute_amount_and_tdg` so it uses `rubric` (keeps identical output; removes the duplicate formula):
```python
from ..rubric import amount_and_tdg_from_time, format_tdg, tdg_for

def _compute_amount_and_tdg(contribution_type, hours, minutes, usd):
    if contribution_type == "Time":
        return amount_and_tdg_from_time(hours, minutes)
    else:  # USD
        val = usd or 0
        return f"{val:.2f}", format_tdg(tdg_for("USD", val))
```
(Leave its `main()` and arg parsing untouched — it already has no `--tdg-issued`.)

---

## 4. Tests (add under `tests/`, pytest — §9 test-before-merge)

**`tests/test_rubric.py`** (pure, no env):
```python
import pytest
from truesight_dao_client.rubric import tdg_for, format_tdg, amount_and_tdg_from_time, parse_amount

def test_time_minutes():
    assert tdg_for("Time (Minutes)", 60) == 100.0
    assert tdg_for("Time (Minutes)", 45) == 75.0
    assert tdg_for("Time (Minutes)", 30) == 50.0
    assert format_tdg(tdg_for("Time (Minutes)", 35)) == "58.33"   # 35/60*100

def test_usd_and_usdt_one_to_one():
    assert tdg_for("USD", 27.70) == 27.70
    assert tdg_for("USDT received", 100) == 100.0   # confirm USDT policy (OPEN DECISION)

def test_amount_and_tdg_from_time():
    assert amount_and_tdg_from_time(0, 45) == ("45", "75.00")
    assert amount_and_tdg_from_time(1, 30) == ("90", "150.00")

def test_unknown_type_raises():
    with pytest.raises(ValueError):
        tdg_for("Software", 10)

def test_amount_parsing():
    assert parse_amount("$1,234.50") == 1234.50
    with pytest.raises(ValueError):
        parse_amount("abc")
```

**`tests/test_report_contribution_tdg.py`** — the derive function is pure, test it directly (no env, no network):
```python
from truesight_dao_client.modules.report_contribution import _authoritative_tdg

def test_wrong_tdg_is_overridden(capsys):
    attrs = [("Type", "Time (Minutes)"), ("Amount", "45"),
             ("Contributor(s)", "Gary Teh"), ("TDG Issued", "750")]
    out = dict(_authoritative_tdg(attrs))
    assert out["TDG Issued"] == "75.00"                 # computed, not 750
    assert "IGNORED" in capsys.readouterr().err          # warned

def test_tdg_inserted_when_absent():
    attrs = [("Type", "Time (Minutes)"), ("Amount", "60"), ("Contributor(s)", "Gary Teh")]
    out = dict(_authoritative_tdg(attrs))
    assert out["TDG Issued"] == "100.00"

def test_matching_tdg_no_warning(capsys):
    attrs = [("Type", "Time (Minutes)"), ("Amount", "45"),
             ("Contributor(s)", "Gary Teh"), ("TDG Issued", "75.00")]
    _authoritative_tdg(attrs)
    assert "IGNORED" not in capsys.readouterr().err
```

**Run:** `pytest tests/test_rubric.py tests/test_report_contribution_tdg.py -q` (and the existing suite stays green).

---

## 5. Manual verify (before merge)

From `dao_client/` with `.venv` active and a valid `.env`:
```bash
# Bogus --tdg-issued must be ignored, payload shows the computed value, stderr warns:
truesight-dao-report-contribution --type "Time (Minutes)" --amount 45 \
  --tdg-issued 750 --contributors "Gary Teh" --description "test" --dry-run
```
**Expect:** dry-run payload line `- TDG Issued: 75.00`; a stderr line `--tdg-issued 750 IGNORED; using rubric value 75.00 …`. Repeat without `--tdg-issued` → same `75.00`. Try `--amount 35` → `58.33`. Omit `--amount` → friendly `Missing required field(s): Amount`.

---

## 6. Scope, PR, contribution, resume

- **ONE PR** in `TrueSightDAO/dao_protocol`. Files (all under the Python client subtree `truesight_dao_client/`): `rubric.py` (new), `edgar_client.py` (derive hook), `modules/report_contribution.py` (derive + required Amount), `modules/report_ai_agent_contribution.py` (delegate to rubric), `tests/test_rubric.py` + `tests/test_report_contribution_tdg.py` (new).
- **PR body must state:** TDG is now computed client-side from Type+Amount; `--tdg-issued` is ignored-with-warning (option a); `Amount` is now required on `report_contribution`; USDT rubric is a flagged OPEN DECISION defaulted to 1:1.
- After merge, **report the DAO contribution** (§6 OPERATING_INSTRUCTIONS).
- **§8 note:** OPERATING_INSTRUCTIONS §8 (npm version bump) only triggers on changes under `packages/dao-client/`. This PR touches only `truesight_dao_client/` (the Python client), so **§8 does not apply** — do **not** bump `packages/dao-client/package.json`. §8 applies only to the Appendix follow-up.

> ## ▶ RESUME HERE
> Build §3.1→§3.4 + §4 tests as one PR in `TrueSightDAO/dao_client`. Confirm the USDT rubric with Gary
> (§3.1 OPEN DECISION). Verify per §5, open the PR per §6, report the contribution, STOP.

✅ **Pre-flight Completeness (§5d):** all code, file paths, line anchors, and the formula are in this doc; no execution turn needs to read another file to build it.

---

## Appendix — "later" (NOT this PR): one rubric for the whole stack
Gary flagged single-source-of-truth as a later item. Conveniently, the npm package lives in **this same repo** (`packages/dao-client/`), so unification is in-repo. End-state: the formula lives in ONE governed place and every client consumes it:
- Put the rubric in the **npm `@truesight_dao/dao-client`** package (`packages/dao-client/`) — **§8 version bump required** since that subtree changes — and have the **dapp** import it instead of its inline JS.
- Have this Python `rubric.py` mirror that package's constants (or generate both from a shared rubric JSON the DAO governs, so a rate change is a one-place edit).
- Audit any other consumer (oracle, Butterfly Effect Club) that computes TDG.
Until then, `rubric.py` here + the dapp JS must be kept in lockstep manually (they already match at 100/hr, USD 1:1).
