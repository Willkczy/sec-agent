from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API target (securities-recommendation services)
    API_BASE_URL: str = "http://localhost:8089"
    FIN_ENGINE_BASE_URL: str | None = None
    MODEL_PORTFOLIO_BASE_URL: str | None = None

    # LLM (self-hosted GPU, OpenAI-compatible)
    LLM_BASE_URL: str = "http://103.42.51.88:2205/"
    LLM_API_KEY: str = "anything works"
    LLM_MODEL: str = "orchestrator"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 16384

    # Auth toggle (False for local, True for deployed)
    ENABLE_AUTH: bool = False

    # Local mode: strips /cr/src, /cr/fin-engine, etc. prefixes from endpoints
    # Set to true when running backend services locally without a reverse proxy
    LOCAL_MODE: bool = False

    # Glass-Box reasoning architecture: "two_layer" or "three_layer".
    # two_layer  = Reasoner + Answerer (default).
    # three_layer = adds a Verifier with up to 2 retries (slower, stricter).
    REASONING_ARCHITECTURE: str = "two_layer"

    # Logging — see logging_config.py.
    # LOG_FORMAT=pretty draws a per-request box with stage indents;
    # LOG_FORMAT=plain emits one flat line per record (for aggregators).
    # LOG_USE_UNICODE=false swaps box/marker glyphs for ASCII fallbacks.
    # LOG_HTTP_BODIES is reserved for PR 2 (DEBUG-gated raw payload logging).
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "pretty"
    LOG_USE_UNICODE: bool = True
    LOG_COLOR: bool = False
    LOG_HTTP_BODIES: bool = False

    # The same .env is also used by the imported Glass-Box models, which read
    # vars such as MODEL_PROVIDER, GPU_BASE_URL, and OPENAI_API_KEY directly
    # from os.environ. Ignore those here instead of failing Settings startup.
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
