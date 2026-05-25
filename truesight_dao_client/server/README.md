# dao_protocol server (`[server]` extra)

The HTTP half of this repo. It hosts the FastAPI service that is gradually
taking over the DAO/Agroverse integration surface from the Rails
`sentiment_importer` (Edgar) app — reusing this package's canonical-payload +
RSA logic (`edgar_client.py`) so the signer and verifier share one source of
truth.

This is **optional**. The CLI install stays lean; the server deps only arrive
with the extra:

```bash
pip install truesight-dao-client            # client + CLIs only
pip install -e '.[server]'                  # + FastAPI / uvicorn / pydantic-settings
```

## Run locally

```bash
truesight-dao-protocol-server               # reads DAO_PROTOCOL_* env / .env
# or
uvicorn truesight_dao_client.server.main:app --port 8010
curl localhost:8010/ping
```

## Layout

```
server/
  main.py            # FastAPI app factory + uvicorn entrypoint
  config.py          # DAO_PROTOCOL_* settings (pydantic-settings)
  routes/health.py   # /ping + /healthz   (PR1 plumbing-proof slice)
  deploy/            # deploy.sh + systemd unit (seni_ror_new:8010)
```

## Status

**PR1** ships the scaffold + health endpoint only. Later slices add
`crypto/verify.py`, the `sheets/` adapters, and the per-route handlers in the
strangler-fig order documented in
`agentic_ai_context/EDGAR_DAO_EXTRACTION_PLAN.md`. The nginx flip on `krake_ng`
that routes a path to this service is a separate, deliberate ops step per PR.
