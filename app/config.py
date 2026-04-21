from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    openai_api_key: str
    admin_api_key: str
    cors_origins: str = "http://localhost:3000"
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

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
