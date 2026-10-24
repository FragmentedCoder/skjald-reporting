from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the environment (see deploy/.env.example)."""

    model_config = SettingsConfigDict(env_prefix="SKJALD_")

    data_dir: str = "/data"
    master_key_path: str = "/etc/skjald/master.key"
    # The address people open Skjald at. Passkeys are bound to its host name,
    # which must be a name, not an IP address.
    address: str = "https://localhost"


settings = Settings()
