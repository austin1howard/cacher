from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CACHER_")

    allowed_hosts: list[str] = []
    max_cache_entries: int = Field(default=1000, gt=0)
    max_response_body_bytes: int = Field(default=10 * 1024 * 1024, gt=0)

    @field_validator("allowed_hosts")
    @classmethod
    def must_not_be_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("CACHER_ALLOWED_HOSTS must be set to a non-empty list")
        return v


settings = Settings()
