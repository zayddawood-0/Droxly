from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Env-var-driven settings (specs/security.md §8 — secrets injected at
    runtime, never hardcoded). Only what this phase's health check and
    migration tooling actually need — auth/provider/storage settings are
    added by the phases that introduce them (FR-AUTH-*, FR-PROC-*, ...),
    not scaffolded speculatively here.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "local"
    database_url: str = "postgresql+asyncpg://doxly:doxly@localhost:5432/doxly"

    # decisions.md ADR-012/OQ-03: EmbeddingProvider is mandatory, provider
    # choice is configurable. "fake" (deterministic, offline, zero-cost) is
    # the default until an OpenAI key is supplied — resolved for local/dev
    # use per OQ-03's "confirm before Phase 6" note; swapping to "openai"
    # requires openai_api_key and changes nothing else (app/ai/embeddings.py).
    embedding_provider: str = "fake"
    openai_api_key: str | None = None

    # decisions.md ADR-011/OQ-02: LLMProvider is mandatory, provider choice
    # is configurable. "fake" (deterministic, scriptable, zero-cost) is the
    # default until an Anthropic key is supplied, and is also the required
    # provider for LangGraph node tests (testing.md §4.1's "LLM call
    # mocked" requirement).
    llm_provider: str = "fake"
    anthropic_api_key: str | None = None

    # --- R1 (tasks/remediation-plan.md) — auth, CSRF, rate limiting ---

    # decisions.md ADR-010: HS256-signed access tokens. A real deployment
    # must override this via the JWT_SIGNING_KEY env var (security.md §8 —
    # secrets are never committed); the fallback exists only so local dev
    # doesn't require generating a secret before the app can start, matching
    # database_url's same placeholder-default pattern above.
    jwt_signing_key: str = "local-dev-insecure-signing-key-do-not-use-in-production"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # decisions.md ADR-010 / OQ-01 — Google OAuth2. None until configured;
    # the oauth router endpoints return oauth_not_configured rather than
    # failing unpredictably when these are unset (true in every environment
    # this remediation task was implemented/tested in).
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    # The frontend origin OAuth redirects land on after FastAPI's callback
    # sets cookies (deployment.md §5.1's NEXT_PUBLIC_API_BASE_URL's sibling
    # on the frontend side) — kept separate from any single hardcoded URL so
    # this works unchanged across local/preview/production per deployment.md §10.
    frontend_base_url: str = "http://localhost:3000"

    # api.md §0.7 / decisions.md OQ-08 — Redis token-bucket rate limiting,
    # reusing ADR-008's Redis instance rather than provisioning a second one.
    redis_url: str = "redis://localhost:6379"

    # observability.md §6 / remediation-plan.md R1 §4.1 — a minimal
    # EmailProvider abstraction (decisions.md ADR-020), mirroring
    # llm_provider/embedding_provider's "fake by default" pattern above so
    # email-dependent flows (FR-AUTH-002 verification, FR-AUTH-007 reset)
    # are testable offline without a real mail server.
    email_provider: str = "fake"
    email_from_address: str = "no-reply@doxly.local"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None

    # --- R2 (tasks/remediation-plan.md) — document storage ---

    # decisions.md ADR-009: StorageProvider is mandatory. Provider is
    # Cloudflare R2 (OQ-04, resolved 2026-08-31). "local" (a real,
    # working filesystem-backed implementation — not a mock) remains the
    # active default until real R2 credentials are supplied, matching
    # llm_provider/embedding_provider/email_provider's identical "fake/local
    # by default" pattern. Documented as decisions.md ADR-022.
    storage_provider: str = "local"
    # Where LocalFilesystemStorageProvider writes uploaded bytes — never
    # committed, gitignored like any other local runtime data.
    storage_local_dir: str = "./.local-storage"
    storage_presigned_url_expires_in_seconds: int = 900
    # FastAPI's own externally-reachable origin — needed only to construct
    # LocalFilesystemStorageProvider's presigned URLs, which (per ADR-009)
    # must point directly at wherever bytes get received, never through the
    # Next.js BFF (deployment.md §7's "the actual file bytes never transit
    # Vercel or FastAPI" — the BFF specifically). Distinct from
    # frontend_base_url, which is the Next.js origin and would be the wrong
    # target for a direct-upload URL even in local dev.
    backend_public_base_url: str = "http://localhost:8000"

    # decisions.md OQ-04 (resolved) — R2StorageProvider's own config, unused
    # while storage_provider="local". R2's S3-compatible endpoint is
    # account-specific (unlike AWS S3's fixed regional endpoints), so unlike
    # a real AWS deployment this must always be set explicitly once
    # storage_provider="r2" — there is no usable default to fall back to.
    storage_endpoint_url: str | None = None
    storage_bucket_name: str | None = None
    storage_access_key_id: str | None = None
    storage_secret_access_key: str | None = None

    # --- R3 remediation (tasks/R3-document-processing.md, decisions.md
    # ADR-026) — worker-crash recovery ---
    # A document stuck in a non-terminal processing stage (queued/
    # extracting/chunking/embedding) longer than this is treated as
    # reprocessable, same as one already `failed` (api.md's reprocess
    # entry). 900s (15 min) — no spec-defined threshold existed; chosen as
    # a documented multiple of `performance.md` NFR-PERF-004's 60s p95 for
    # a *typical* 20-page document, generous enough that a legitimately
    # large (up to the 25MB ceiling) document in progress is very unlikely
    # to be misidentified as stuck. See ADR-026 for the full reasoning.
    document_processing_stale_threshold_seconds: int = 900

    # --- R12 (tasks/remediation-plan.md) — production deployment readiness ---

    # deployment.md §5.1/§11 — comma-separated list of origins permitted to
    # call the API. Locked to the exact production frontend domain(s) in
    # production (never a wildcard, per §11); defaults to the local Next.js
    # dev origin so a fresh clone works unauthenticated-CORS-wise out of the
    # box, matching every other setting's "safe local default" convention.
    cors_allowed_origins: str = "http://localhost:3000"

    # deployment.md §5.1/§10 — per-environment log verbosity (`debug`
    # locally, `info`/`warning` in production). core/logging.py's
    # configure_logging() is the only reader.
    log_level: str = "info"

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.cors_allowed_origins.split(",")
            if origin.strip()
        ]


settings = Settings()
