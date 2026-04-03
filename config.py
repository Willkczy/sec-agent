from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API target (securities-recommendation services)
    API_BASE_URL: str = "http://localhost:8089"

    # LLM (self-hosted GPU, OpenAI-compatible)
    LLM_BASE_URL: str = "http://103.42.51.88:2205/"
    LLM_API_KEY: str = "anything works"
    LLM_MODEL: str = "orchestrator"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 16384

    # Auth toggle (False for local, True for deployed)
    ENABLE_AUTH: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
