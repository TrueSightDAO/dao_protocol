#!/usr/bin/env python3
"""Event dispatch — port of Rails `dao_controller#trigger_immediate_processing`.

After a verified submission is logged, fire the GAS webhook(s) for its event type (immediate
processing; the GAS cron is the fallback when a webhook URL isn't configured — same as Rails).
First-matching tag wins (mirrors the Rails `if/elsif` chain). Webhook URLs come from env
(`DAO_PROTOCOL_WEBHOOK_<KEY>`), provisioned in the box `.env` server-side; missing → skipped + logged.

Runs in a FastAPI BackgroundTask (non-user-visible propagation), so it never blocks/breaks the
synchronous intake response.
"""

from __future__ import annotations

import logging
import os
import re

from .jobs import inventory_snapshot, webhook_trigger

logger = logging.getLogger("dao_protocol.dispatch")


def _extract_field(text: str, label: str) -> str | None:
    """Extract a field value from the submission text header (before the first -------- divider)."""
    norm = re.sub(r"\r\n?", "\n", text or "")
    header = norm.split("\n--------", 1)[0]
    m = re.search(rf"(?im)^-\s*{re.escape(label)}:\s*(.+)$", header)
    return m.group(1).strip() if m else None


# Ordered: (event-tag or tuple-of-tags, [(env_key, action), …], enqueue_inventory_snapshot).
# First matching entry wins. Mirrors dao_controller#trigger_immediate_processing exactly.
ROUTING: list = [
    # Inventory snapshot fires on these three too — Rails sets enqueue_agroverse_inventory_snapshot:
    # true on SALES_AGL4, SALES_NON_AGL4, INVENTORY_PROCESSING, EXPENSE_PROCESSING (collapsed here
    # to one event-level enqueue, since the snapshot worker is unique:until_and_while_executing
    # so stacked enqueues already coalesce to one publish on Rails).
    (
        "[SALES EVENT]",
        [
            ("SALES_PROCESSING", "parseTelegramChatLogs"),
            ("SALES_AGL4", "processTokenizedTransactions"),
            ("SALES_NON_AGL4", "processNonAgl4Transactions"),
        ],
        True,
    ),
    (
        "[INVENTORY MOVEMENT]",
        [("INVENTORY_PROCESSING", "processTelegramChatLogs")],
        True,
    ),
    (
        "[DAO Inventory Expense Event]",
        [("EXPENSE_PROCESSING", "parseAndProcessTelegramLogs")],
        True,
    ),
    (
        "[QR CODE UPDATE EVENT]",
        [("QR_CODE_UPDATE", "processQrCodeUpdatesFromTelegramChatLogs")],
        False,
    ),
    (
        "[DAPP PERMISSION CHANGE EVENT]",
        [("DAPP_PERMISSION_CHANGE", "apply_permission_change")],
        False,
    ),
    ("[WARMUP SEND EVENT]", [("WARMUP_SEND", "apply_warmup_send")], False),
    (
        "[BATCH QR CODE REQUEST]",
        [("QR_CODE_GENERATION", "processQRCodeGenerationTelegramLogs")],
        False,
    ),
    (
        ("[PROPOSAL CREATION]", "[PROPOSAL VOTE]"),
        [("PROPOSAL_PROCESSING", "process_dapp_payloads")],
        False,
    ),
    (
        "[REPACKAGING BATCH EVENT]",
        [("REPACKAGING_PROCESSING", "processRepackagingBatchesFromTelegramChatLogs")],
        False,
    ),
    (
        "[CURRENCY CONVERSION EVENT]",
        [("CURRENCY_CONVERSION_PROCESSING", "parseAndProcessCurrencyConversionLogs")],
        False,
    ),
    (
        "[RETAIL FIELD REPORT EVENT]",
        [
            (
                "RETAIL_FIELD_REPORT_PROCESSING",
                "processRetailFieldReportsFromTelegramChatLogs",
            )
        ],
        False,
    ),
    (
        "[STORE ADD EVENT]",
        [("STORE_ADD_PROCESSING", "processStoreAddsFromTelegramChatLogs")],
        False,
    ),
    (
        "[DONATION MINT EVENT]",
        [("DONATION_MINT_PROCESSING", "processDonationMintsFromTelegramChatLogs")],
        False,
    ),
    (
        "[PARTNER ADD EVENT]",
        [("PARTNER_ADD_PROCESSING", "processPartnerAddsFromTelegramChatLogs")],
        False,
    ),
    (
        "[CONTRIBUTOR ADD EVENT]",
        [
            (
                "CONTRIBUTOR_ADD_PROCESSING",
                "processContributorAddsFromTelegramChatLogs",
            ),
            ("ONBOARDING_INVITATION", "sendOnboardingInvitation"),
        ],
        False,
    ),
    (
        "[CREDENTIALING ATTESTATION EVENT]",
        [("CREDENTIALING_ATTESTATION", "process_attestation_events")],
        False,
    ),
    (
        "[PARTNER CHECK-IN EVENT]",
        [("PARTNER_CHECK_IN_PROCESSING", "processPartnerCheckInsFromTelegramChatLogs")],
        False,
    ),
    (
        "[REPACKAGING SETTLEMENT EVENT]",
        [
            ("POST_REPACKAGING_CLEANUP", "processPostRepackagingCleanup"),
        ],
        True,
    ),  # enqueue inventory snapshot (writes to offchain asset location)
    (
        "[ASSET RECEIPT EVENT]",
        [("ASSET_RECEIPT_PROCESSING", "processAssetReceiptsFromTelegramChatLogs")],
        True,
    ),
    # Self-serve program onboarding (step 1). Scanner appends a PENDING row to the
    # `Program Registrations` tab; a governor approves in step 2 before provisioning.
    # Spec: agentic_ai_context/PROGRAM_PARTNER_ONBOARDING.md.
    (
        "[PROGRAM REGISTRATION REQUEST]",
        [
            (
                "PROGRAM_REGISTRATION_PROCESSING",
                "processProgramRegistrationsFromTelegramChatLogs",
            )
        ],
        False,
    ),
    # Review events — processed by the GAS processApprovalRejections webhook
    (
        "[CONTRIBUTION REVIEW EVENT]",
        [("REVIEW_PROCESSING", "processApprovalRejections")],
        False,
    ),
    # Currency definition — defines a QR-ready serializable currency in the Currencies tab
    (
        "[CURRENCY DEFINITION EVENT]",
        [("CURRENCY_DEFINITION", "processCurrencyDefinitionsFromTelegramChatLogs")],
        False,
    ),
    # White-label design events — deduped via Design Events tab, processed by GAS
    ("[DESIGN UPLOAD EVENT]", [("DESIGN_PROCESSING", "processDesignEvents")], False),
    (
        "[DESIGN ORDER EVENT]",
        [("DESIGN_ORDER_PROCESSING", "processDesignOrderEvents")],
        False,
    ),
    # Governor-only: links a Sunmint [TREE PLANTING EVENT] submission to a sold Agroverse QR code.
    # Handler (tokenomics process_tree_planting_link.js) has its own cron fallback + real governor
    # enforcement — this entry is purely a latency optimization, same as every other row here.
    # Spec: agentic_ai_context/plans/SUNMINT_TREE_QR_LINKING_PLAN.md (PR5).
    (
        "[TREE PLANTING REJECT EVENT]",
        [
            ("TREE_PLANTING_REJECT", "processTreePlantingLinksFromTelegramChatLogs"),
        ],
        False,
    ),
    (
        "[TREE PLANTING LINK EVENT]",
        [
            ("TREE_PLANTING_LINK", "processTreePlantingLinksFromTelegramChatLogs"),
        ],
        False,
    ),
    # Farmer-submitted plain tree planting event (site index page -> [TREE PLANTING EVENT]).
    # GAS handler (tokenomics process_tree_planting_telegram_logs.js) scans Telegram Chat Logs,
    # dedups by message/file ID, appends to the SunMint Tree Planting tab (the tree index
    # builder reads this tab). Same latency-optimization pattern as every other row.
    (
        "[TREE PLANTING EVENT]",
        [
            ("TREE_PLANTING_PROCESSING", "processTreePlantingTelegramLogs"),
        ],
        False,
    ),
    # Farmer-submitted tree growth monitoring measurement (photo + calibration card).
    # GAS handler mirrors photos to TrueSightDAO/sunmint images/growth/, the GitHub Action
    # runs PM002 analysis and commits analysis.json; handler appends the measurement row
    # (Tree Growth Measurements tab), writes per-tree JSON history, logs to Telegram Chat Logs.
    (
        "[TREE GROWTH MONITORING EVENT]",
        [
            (
                "TREE_GROWTH_MONITORING",
                "processTreeGrowthMonitoringFromTelegramChatLogs",
            ),
        ],
        False,
    ),
    # Farmer-submitted geotagged plot boundary evidence (photos/videos of boundary markers).
    # GAS handler (to be added: process_farm_boundary_telegram_logs) mirrors media to
    # TrueSightDAO/sunmint images/<plot_id>/, the extraction script (sunmint/scripts/extract_plot_gps.py)
    # builds the approx hull polygon, and the backend upserts the farm + plot row in the SunMint
    # Farms sheet (new farm name -> auto-create farm record, per SUNMINT_BOUNDARY_SUBMISSION_PLAN rule 4).
    (
        "[FARM BOUNDARY EVIDENCE EVENT]",
        [
            (
                "FARM_BOUNDARY_EVIDENCE",
                "processFarmBoundaryEvidenceFromTelegramChatLogs",
            ),
        ],
        False,
    ),
    # MEDIA RETRACTION EVENT - invalidate boundary media (3-tier: farmer/lead, governor, sentinel).
    # Soft-invalidate: keep the row, set invalidated_at/by/reason/source, drop the item's GPS from
    # the convex hull, recalculate the plot polygon, regenerate plots/index.geojson.
    # See plans/SUNMINT_MEDIA_INVALIDATION_DESIGN.md (agentic_ai_context).
    (
        "[MEDIA RETRACTION EVENT]",
        [
            (
                "MEDIA_RETRACTION",
                "processMediaRetractionFromTelegramChatLogs",
            ),
        ],
        False,
    ),
]


def _webhook_url(env_key: str) -> str:
    return os.environ.get(f"DAO_PROTOCOL_WEBHOOK_{env_key}", "").strip()


def dispatch_event(text: str) -> None:
    text = text or ""
    for tags, targets, enqueue_inventory in ROUTING:
        tag_tuple = tags if isinstance(tags, tuple) else (tags,)
        if any(tag in text for tag in tag_tuple):
            for env_key, action in targets:
                url = _webhook_url(env_key)
                if not url:
                    logger.warning(
                        "no webhook URL for %s (set DAO_PROTOCOL_WEBHOOK_%s) — GAS cron will process",
                        action,
                        env_key,
                    )
                    continue
                # Onboarding invitation needs extra params beyond just ?action=
                if env_key == "ONBOARDING_INVITATION":
                    secret = os.environ.get(
                        "DAO_PROTOCOL_WEBHOOK_EMAIL_VERIFICATION_SECRET", ""
                    ).strip()
                    params = {
                        "action": action,
                        "secret": secret,
                        "email": _extract_field(text, "Contributor Email") or "",
                        "contributor_name": _extract_field(text, "Contributor Name")
                        or "",
                        "inviter_name": _extract_field(text, "Governor Name") or "",
                        "inviter_email": _extract_field(text, "Governor Email") or "",
                    }
                    webhook_trigger.trigger_with_params(url, params, description=action)
                else:
                    webhook_trigger.trigger(url, action)
            if enqueue_inventory:
                # Rails enqueues AgroverseInventorySnapshotPublishWorker after a ledger webhook
                # succeeds (refresh the public inventory JSON). It's a GET ?action=&token=.
                inventory_snapshot.publish()
            return  # first-match-wins (Rails if/elsif)
    logger.info("dispatch: no event-tag routing matched")
