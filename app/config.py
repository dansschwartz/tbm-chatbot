import os
import sys

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    openai_api_key: str = ""
    admin_api_key: str = "change-me"
    cors_origins: str = "*"
    log_level: str = "INFO"

    # Rate limiting
    rate_limit_per_session: int = 20  # messages per minute per session
    rate_limit_per_tenant: int = 200  # messages per minute per tenant

    # RAG settings
    embedding_model: str = "text-embedding-3-small"
    chat_model: str = "gpt-4o-mini"
    chunk_size: int = 500  # tokens
    chunk_overlap: int = 50  # tokens
    top_k_chunks: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


try:
    settings = Settings()
    if not settings.database_url:
        print("ERROR: DATABASE_URL environment variable is not set!", file=sys.stderr)
        sys.exit(1)
    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable is not set!", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"ERROR loading settings: {e}", file=sys.stderr)
    sys.exit(1)
