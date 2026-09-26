from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Our AI"
    app_version: str = "0.3.0"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:1.7b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_think: bool = False

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/our_ai"
    )

    default_project_id: str = (
        "00000000-0000-0000-0000-000000000001"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
