"""
Application configuration
"""
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings"""
    
    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8080
    API_TITLE: str = "Reforge API"
    API_VERSION: str = "0.1.0"
    
    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "reforge"
    POSTGRES_USER: str = "reforge"
    POSTGRES_PASSWORD: str = "reforge_pw"
    
    # Redis
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    
    # Workers
    BUILDER_WORKSPACE: str = "/tmp/reforge_builds"
    ARTIFACTS_PATH: str = "/files/artifacts"
    
    # LLM / OpenRouter
    OPENROUTER_API_KEY: str | None = None
    
    # Build Defaults
    DEFAULT_BUILD_TIMEOUT: int = 600  # seconds
    
    @property
    def database_url(self) -> str:
        """PostgreSQL connection string"""
        return f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @property
    def redis_url(self) -> str:
        """Redis connection string"""
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
