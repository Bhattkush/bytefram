from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(__file__).resolve().parents[1]
    weather_api_key: str = os.getenv("OPENWEATHER_API_KEY", "").strip()
    weather_base_url: str = os.getenv(
        "OPENWEATHER_BASE_URL", "https://api.openweathermap.org/data/2.5"
    )
    model_dir: Path = Path(os.getenv("MODEL_DIR", "ML/models"))
    db_path: Path = Path(os.getenv("DB_PATH", "database/crop_yield.db"))
    allowed_origins: tuple[str, ...] = tuple(
        part.strip()
        for part in os.getenv("ALLOWED_ORIGINS", "*").split(",")
        if part.strip()
    )

    @property
    def resolved_model_dir(self) -> Path:
        if self.model_dir.is_absolute():
            return self.model_dir
        return (self.project_root / self.model_dir).resolve()

    @property
    def resolved_db_path(self) -> Path:
        if self.db_path.is_absolute():
            return self.db_path
        return (self.project_root / self.db_path).resolve()


settings = Settings()
