import os
import pytest

# Configure non-production test environment defaults for isolated unit tests
os.environ["CHENNALINK_ENV"] = "test"
os.environ["ALLOW_LOCAL_FALLBACK"] = "true"
os.environ["DB_BACKEND"] = "sqlite"
os.environ["STORAGE_BACKEND"] = "local"

from backend.config import settings
settings.chennalink_env = "test"
settings.allow_local_fallback = True
settings.db_backend = "sqlite"
settings.storage_backend = "local"
