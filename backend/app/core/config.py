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


settings = Settings()
