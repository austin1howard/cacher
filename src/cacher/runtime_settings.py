import asyncio

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CACHER_")

    allowed_hosts: list[str] = []


class CachedResponse(BaseModel):
    model_config = {"frozen": True}

    body: bytes
    content_type: str
    status_code: int


settings = Settings()
cache: dict[str, CachedResponse] = {}
lock = asyncio.Lock()
