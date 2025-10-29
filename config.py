# config.py
import os
from dotenv import load_dotenv
from fastapi import HTTPException

load_dotenv()

def validate_environment():
    required = ["OPENAI_API_KEY", "REDIS_URL"]
    missing = [v for v in required if not os.getenv(v)]
    if missing:
        raise HTTPException(status_code=500,
            detail=f"Missing required environment variables: {', '.join(missing)}")

class Settings:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
    MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", 50_000_000))  # 50MB
    ALLOWED_EXTENSIONS = [".zip"]

settings = Settings()