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


settings = Settings()
