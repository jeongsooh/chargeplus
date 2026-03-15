from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    REDIS_URL: str = "redis://redis:6379/0"
    GATEWAY_HOST: str = "0.0.0.0"
    GATEWAY_PORT: int = 9000
    OCPP_SECURITY_PROFILE: int = 0
    RESPONSE_TIMEOUT: float = 10.0

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
