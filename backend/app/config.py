from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "BosoDrive Optimizer API"
    database_url: str = "sqlite:///./bosodrive.db"
    cors_origins: str = "http://localhost:3000"
    google_maps_api_key: str = ""
    run_migrations_on_startup: bool = False
    run_seed_on_startup: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_startup_contract(self) -> None:
        missing: list[str] = []
        if not self.google_maps_api_key.strip():
            missing.append("GOOGLE_MAPS_API_KEY")
        if not self.cors_origin_list:
            missing.append("CORS_ORIGINS")
        if missing:
            missing_values = ", ".join(missing)
            raise RuntimeError(
                f"Missing required startup configuration: {missing_values}"
            )


settings = Settings()
