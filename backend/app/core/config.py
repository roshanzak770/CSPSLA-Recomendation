from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    hf_token: str = ""
    database_url: str = "postgresql://user:password@postgres:5432/cloudsla"
    redis_url: str = "redis://redis:6379/0"
    libretranslate_url: str = "http://libretranslate:5000"
    chroma_persist_dir: str = "./chromadb"
    chroma_host: str = "chromadb"
    chroma_port: int = 8000
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 465
    smtp_user: str = ""
    smtp_password: str = ""
    secret_key: str = "change_me_in_production"
    environment: str = "development"
    log_level: str = "INFO"
    pricing_refresh_cron: str = "0 2 * * *"
    sla_refetch_cron: str = "0 2 * * 0"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
