from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Our AI"
    app_version: str = "0.5.0"

    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:1.7b"
    ollama_embedding_model: str = "qwen3-embedding:0.6b"
    ollama_think: bool = False
    ollama_timeout_seconds: float = 120.0
    ollama_num_predict: int = 256
    ollama_num_ctx: int = 4096
    ollama_keep_alive: str = "30m"
    chat_history_messages: int = 8

    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/our_ai"
    )

    default_project_id: str = (
        "00000000-0000-0000-0000-000000000001"
    )

    action_tracker_enabled: bool = False
    action_tracker_base_url: str = "http://127.0.0.1:8000"
    action_tracker_token: str = ""
    action_tracker_default_user: str = ""
    action_tracker_timeout_seconds: float = 20.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
