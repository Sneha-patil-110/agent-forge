from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "AgentForge"
    LOG_LEVEL: str = "INFO"

    GOOGLE_API_KEY: str | None = None
    OPENROUTER_API_KEY: str | None = None
    GROQ_API_KEY: str | None = None
    NVIDIA_API_KEY: str | None = None
    CLOUDFLARE_API_TOKEN: str | None = None
    CLOUDFLARE_ACCOUNT_ID: str | None = None
    ZAI_API_KEY: str | None = None
    CEREBRAS_API_KEY: str | None = None
    PERPLEXITY_API_KEY: str | None = None
    MISTRAL_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None

    LANGSMITH_TRACING: bool = False
    LANGSMITH_API_KEY: str | None = None
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_PROJECT: str = "AgentForge"

    DATABASE_URL: str | None = None
    TEST_DATABASE_URL: str | None = None

    JWT_SECRET: str | None = None
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    API_CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    RATE_LIMIT_RUN_CREATION_PER_MINUTE: int = 5
    RATE_LIMIT_RUN_RESUME_PER_MINUTE: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()