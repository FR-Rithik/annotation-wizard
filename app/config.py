from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "road-damage-api"
    debug: bool = False

    postgres_user: str = "road_user"
    postgres_password: str = "road_pass"
    postgres_db: str = "road_db"
    postgres_host: str = "db"
    postgres_port: int = 5432

    admin_api_key: str

    
    model_path: str = "best.onnx"
    model_confidence_threshold: float = 0.25
    model_imgsz: int = 640
    max_upload_bytes: int = 1 * 1024 * 1024  # 1 MB
    max_image_pixels: int = 16_000_000

    # Dataset labeling limits
    max_dataset_zip_bytes: int = 50 * 1024 * 1024
    max_dataset_uncompressed_bytes: int = 100 * 1024 * 1024
    max_dataset_images: int = 100
    max_dataset_image_bytes: int = 5 * 1024 * 1024

    database_url_override: str | None = Field(
        default=None,
        validation_alias="DATABASE_URL",
    )

    @field_validator("debug", mode="before")
    @classmethod
    def parse_debug_mode(cls, value: object) -> object:
        """Treat common deployment mode labels as a disabled debug flag."""
        if isinstance(value, str) and value.lower() in {"release", "production"}:
            return False
        return value

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
