from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = BACKEND_ROOT / 'data' / 'app.db'
DEFAULT_DATASET_PATH = PROJECT_ROOT / 'data' / 'people_dataset_v1.json'


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'AI Think Tank Backend'
    debug: bool = False
    api_prefix: str = '/api'
    cors_origins: list[str] = Field(default_factory=lambda: [
        'http://127.0.0.1:8125',
        'http://localhost:8125',
        'http://127.0.0.1:8126',
        'http://localhost:8126',
    ])
    database_url: str = f'sqlite:///{DEFAULT_DB_PATH}'
    deepseek_base_url: str = 'https://api.deepseek.com'
    deepseek_model: str = 'deepseek-chat'
    deepseek_api_key: Optional[str] = None
    max_context_chunks: int = 5
    recommendation_top_k: int = 5
    import_dataset_path: Path = DEFAULT_DATASET_PATH

    @field_validator('cors_origins', mode='before')
    @classmethod
    def split_cors_origins(cls, value: Union[str, list[str]]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(',') if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return Settings()
