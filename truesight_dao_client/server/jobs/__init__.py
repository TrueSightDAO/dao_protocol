"""Background jobs for the dao_protocol server (webhook dispatch, etc.). Run via FastAPI
BackgroundTasks for now (non-user-visible propagation); swap to arq/Redis if durable retries
are needed (see EDGAR_DAO_EXTRACTION_PLAN "Still open")."""
