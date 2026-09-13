from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    secret_key: str = "dev-secret-change-me"
    whisper_model_size: str = "tiny"
    # OCR spawns an ffmpeg (frame extraction) and a tesseract subprocess per
    # video, on top of the already-resident Whisper model -- on a
    # memory-capped instance (Render's free 512MB plan) that combination can
    # exceed the limit. Off by default there; see README.
    enable_ocr: bool = True

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.database_url
        # Render (like Heroku) hands out "postgres://"; SQLAlchemy 2.x needs
        # the "postgresql://" scheme.
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
