import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    chennalink_env: str = "production"
    db_backend: str = "postgres"
    storage_backend: str = "supabase"
    database_url: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_storage_bucket: str = "chennalink-files"
    chennalink_max_file_size_mb: int = 10
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    allow_local_fallback: bool = False
    
    class Config:
        env_file = ".env"
        extra = "ignore"

    def is_production(self) -> bool:
        return self.chennalink_env.strip().lower() in ("production", "prod")

    def validate_production(self) -> None:
        """
        Validates that production environment has required credentials and no silent local fallbacks.
        Raises RuntimeError with a clear message if violated.
        """
        if not self.is_production():
            return

        if self.allow_local_fallback:
            raise RuntimeError(
                "PRODUCTION CONFIGURATION ERROR: 'allow_local_fallback' cannot be True in production. "
                "Silent local SQLite or local file fallback is strictly prohibited."
            )

        if not self.database_url or not self.database_url.startswith("postgres"):
            raise RuntimeError(
                "PRODUCTION CONFIGURATION ERROR: 'DATABASE_URL' is required for Supabase PostgreSQL connection. "
                "SQLite persistence is strictly prohibited in production."
            )

        key = self.supabase_service_role_key or self.supabase_anon_key
        if not self.supabase_url or not key or key in ["dummy", ""]:
            raise RuntimeError(
                "PRODUCTION CONFIGURATION ERROR: Supabase Storage configuration ('SUPABASE_URL' and key) "
                "is required for private bucket 'chennalink-files'. Local file storage is strictly prohibited in production."
            )

settings = Settings()

