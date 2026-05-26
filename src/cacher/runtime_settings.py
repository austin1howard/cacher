import asyncio
from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="")

    allowed_hosts: list[str] = []


@dataclass(frozen=True, slots=True)
class CachedResponse:
    body: bytes
    content_type: str
    status_code: int


settings = Settings()
cache: dict[str, CachedResponse] = {}
lock = asyncio.Lock()
