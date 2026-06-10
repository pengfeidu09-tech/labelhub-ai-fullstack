from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- Database / Security ----
    DATABASE_URL: str = "sqlite:///./labelhub.db"
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    # ---- AI Behavior ----
    AI_MOCK_MODE: bool = False
    AI_PROVIDER: str = "mock"
    AI_MODEL_NAME: str = "mock-v1"
    AI_TIMEOUT_SECONDS: int = 25
    AI_MOCK_FALLBACK: bool = True
    AI_FORCE_JSON: bool = True

    # ---- Generic LLM (OpenAI compatible) ----
    LLM_API_KEY: str = ""
    LLM_API_BASE_URL: str = ""

    # ---- DashScope / Qwen ----
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_MODEL: str = "qwen3.7-plus"
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
