from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CACHER_")

    allowed_hosts: list[str] = []


settings = Settings()
