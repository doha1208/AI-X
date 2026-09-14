from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = "change-me-in-.env"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    database_url: str = "sqlite:///./app.db"

    class Config:
        env_file = ".env"


settings = Settings()
