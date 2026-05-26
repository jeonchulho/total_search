from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    api_key: str = "change-me"
    milvus_host: str = "milvus"
    milvus_port: int = 19530
    milvus_collection: str = "documents"
    milvus_auto_migrate_dim: bool = False
    milvus_backup_prefix: str = "backup"
    embedding_enabled: bool = True
    embedding_provider: str = "hash"
    embedding_model: str = "text-embedding-3-small"
    embedding_bge_model: str = "BAAI/bge-m3"
    embedding_api_base: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_timeout_sec: int = 30
    embedding_max_length: int = 512
    embedding_batch_size: int = 16
    embedding_auto_batch: bool = True
    embedding_max_concurrency: int = 2
    embedding_device: str = "cpu"
    vector_dim: int = 384 # 1024 for bge-m3


settings = Settings()
