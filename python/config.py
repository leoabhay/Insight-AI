from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    mongo_uri: str = "mongodb://localhost:27017/analytics"
    mongo_db: str = "analytics"

    jwt_secret: str = "supersecretkey_change_in_prod"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60

    upload_dir: str = "../uploads"
    max_upload_mb: int = 200
    chunk_size: int = 50_000          # rows per Pandas chunk

    cors_origins: List[str] = ["http://localhost:3000"]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()