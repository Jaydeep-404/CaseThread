import os
import secrets
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv
load_dotenv()


class Settings(BaseSettings):
    """Application settings"""
    APP_NAME: str = "APIs"
    API_PREFIX: str = "/api"
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # MongoDB settings
    MONGODB_URL: str = Field(default="mongodb://localhost:27017", description="MongoDB connection string")
    MONGODB_DB_NAME: str = Field(default="CaseThreadDB", description="MongoDB database name")
    
    # Security settings
    # SECRET_KEY: str = Field(default=secrets.token_hex(32), description="Secret key for JWT")
    SECRET_KEY: str = os.getenv("SECRET_KEY")
    # Development settings
    DEV_MODE: bool = Field(default=True, description="Development mode")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"  # Allow extra fields in environment

    # Helper method to check debug mode from environment
    @classmethod
    def get_debug_mode(cls) -> bool:
        return os.getenv("DEBUG", "False").lower() in ("true", "1", "t")

    # Helper method to check dev mode from environment
    @classmethod
    def get_dev_mode(cls) -> bool:
        return os.getenv("DEV_MODE", "False").lower() in ("true", "1", "t")
    

settings = Settings(
    DEBUG=Settings.get_debug_mode(),
    DEV_MODE=Settings.get_dev_mode(),
    MONGODB_URL=os.getenv("MONGODB_URL", "mongodb://localhost:27017"),
    MONGODB_DB_NAME=os.getenv("MONGODB_DB_NAME", "CaseThreadDB")
)
