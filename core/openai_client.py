"""
OpenAI client configuration and management.
"""
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Global OpenAI client
_openai_client = None


def get_openai_client() -> OpenAI:
    """Get or create OpenAI client instance."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


def validate_openai_key() -> bool:
    """Check if OpenAI key is valid."""
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        return api_key is not None and api_key.startswith("sk-")
    except Exception:
        return False
