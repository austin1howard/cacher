import asyncio
from dataclasses import dataclass

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Stored as a comma-separated string to avoid pydantic-settings JSON-decoding
    # list fields before validators can run. Parse with .allowed_host_list.
    model_config = SettingsConfigDict(env_prefix="")

    allowed_hosts: str = ""

    @property
    def allowed_host_list(self) -> list[str]:
        if not self.allowed_hosts:
            return []
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]


@dataclass(frozen=True, slots=True)
class CachedResponse:
    body: bytes
    content_type: str
    status_code: int


settings = Settings()
cache: dict[str, CachedResponse] = {}
lock = asyncio.Lock()
