from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
    )

    app_env: str = "development"
    host: str = "127.0.0.1"
    port: int = 8010
    secret_key: str = "course-demo-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Database
    database_url: str = f"sqlite:///{ROOT_DIR / 'data' / 'app.db'}"

    # LLM
    llm_mode: str = "api"
    llm_api_key: str = ""
    llm_api_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-v4-flash"
    llm_timeout_seconds: float = 20.0
    llm_temperature: float = 0.2
    llm_max_tokens: int = 500

    # Web search
    web_search_api_key: str = ""
    web_search_api_base: str = "https://api.bochaai.com/v1/web-search"
    web_search_timeout: int = 10
    web_search_max_results: int = 3


settings = Settings()
