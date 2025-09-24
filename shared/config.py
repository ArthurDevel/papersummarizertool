from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import model_validator, Field
from typing import Optional, Any, Dict
import os
import logging

# --- TEMPORARY DEBUGGING ---
# Use logging instead of print to ensure visibility in Railway logs.
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)
log.info("--- Checking environment variables for debugging ---")
log.info(f"Available environment variables: {dict(os.environ)}")
log.info("----------------------------------------------------")
# --- END TEMPORARY DEBUGGING ---

# Load environment variables from .env file.
# `override=True` ensures that the .env file takes precedence over system environment variables.
# load_dotenv(override=True)

class Settings(BaseSettings):
   
    model_config = SettingsConfigDict(
        # If you have a .env file, this will load it.
        # However, it will not override existing environment variables.
        env_file=".env",
        env_file_encoding="utf-8",
        # Pydantic will now prioritize environment variables over .env file values
        # which is the desired behavior for Railway.
        extra="ignore"
    )

    CONTAINERPORT_API: int = 8000
    CONTAINERPORT_FRONTEND: int = 3000
    OPENROUTER_API_KEY: str
    CONTAINERPORT_QDRANT: int = 6333
    CONTAINERPORT_QDRANT_GRPC: int = 6334

    # Vector search related
    VOYAGE_API_KEY: str
    QDRANT_HOST: str
    QDRANT_PORT: int
    QDRANT_API_KEY: str
    
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_HOST: str
    MYSQL_PORT: int = 3306
    MYSQL_DATABASE: str

settings = Settings()

