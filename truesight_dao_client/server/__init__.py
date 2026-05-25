"""HTTP server half of the TrueSight DAO protocol package (``dao_protocol``).

This subpackage is **optional** and only installed via the ``server`` extra::

    pip install truesight-dao-client[server]

It hosts the FastAPI service that takes over the DAO/Agroverse integration
surface currently served by the Rails ``sentiment_importer`` (Edgar) app —
verifying signed payloads with the same canonical-payload + RSA logic the
client half (``edgar_client.py``) uses to *produce* them.

PR1 ships only the scaffold + a health endpoint. Later slices add the Sheets
adapters, signature verification, and the per-route handlers per
``agentic_ai_context/EDGAR_DAO_EXTRACTION_PLAN.md``.
"""
