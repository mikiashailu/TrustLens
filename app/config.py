from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "TrustLens AI API"

    database_url: str = "sqlite:///./data/trustlens.db"
    upload_dir: Path = Path("uploads")
    # Windows: set to e.g. C:\\Program Files\\Tesseract-OCR\\tesseract.exe if not on PATH
    tesseract_cmd: str | None = None


settings = Settings()
