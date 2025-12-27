import os
from pathlib import Path

import data

# Load environment variables from .env file at project root
# This allows for local configuration without modifying system environment variables
try:
    from dotenv import load_dotenv

    # Find project root (parent of 'src' directory)
    current_file = Path(__file__)
    src_dir = current_file.parent.parent  # Go up from env_vars to src
    project_root = src_dir.parent  # Go up from src to project root
    env_file = project_root / ".env"

    if env_file.exists():
        # override=False ensures existing environment variables (like MOCK_S3, MOCK_OPENAI, etc.)
        # are not overwritten by .env file values
        load_dotenv(env_file, override=False)
        print(f"[env_vars] Loaded environment variables from {env_file}")
    else:
        print(
            f"[env_vars] No .env file found at {env_file}, using system environment variables"
        )
except ImportError:
    print(
        "[env_vars] python-dotenv not installed, using system environment variables only. "
        "Install with: pip install python-dotenv"
    )

# Access token
ACCESS_TOKEN_SECRET_KEY = os.environ.get("ACCESS_TOKEN_SECRET_KEY", "").strip()
ACCESS_TOKEN_SECRET_ALGORITHM = os.environ.get(
    "ACCESS_TOKEN_SECRET_ALGORITHM", "HS256"
).strip()
ACCESS_TOKEN_EXPIRE_MINUTES = os.environ.get(
    "ACCESS_TOKEN_EXPIRE_MINUTES", "10080"
).strip()

# OpenAI related
OPENAI_API_KEY = os.environ.get(
    "OPENAI_API_KEY",
    "",
).strip()

OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL",
    "",
).strip()

# Anthropic/Claude related
ANTHROPIC_API_KEY = os.environ.get(
    "ANTHROPIC_API_KEY",
    "",
).strip()

ANTHROPIC_MODEL = os.environ.get(
    "ANTHROPIC_MODEL",
    "",
).strip()

# Azure OpenAI related
AZURE_OPENAI_API_KEY = os.environ.get(
    "AZURE_OPENAI_API_KEY",
    "",
).strip()

AZURE_OPENAI_ENDPOINT = os.environ.get(
    "AZURE_OPENAI_ENDPOINT",
    "",
).strip()

AZURE_OPENAI_DEPLOYMENT = os.environ.get(
    "AZURE_OPENAI_DEPLOYMENT",
    "",
).strip()

AZURE_OPENAI_API_VERSION = os.environ.get(
    "AZURE_OPENAI_API_VERSION",
    "2024-02-15-preview",  # Default to a stable version
).strip()

# PG
PG_USERNAME = os.environ.get("PG_USERNAME", "postgres").strip()
PG_PASSWORD = os.environ.get("PG_PASSWORD", "")
PG_HOST = os.environ.get("PG_HOST", "localhost").strip()
PG_PORT = os.environ.get("PG_PORT", "5432")
PG_DBNAME = os.environ.get("PG_DBNAME", "agentstudy").strip()
PG_SU_USERNAME = os.environ.get("PG_SU_USERNAME", "postgres").strip()
PG_SU_PASSWORD = os.environ.get("PG_SU_PASSWORD", None)

# Local SQLite database file related

SQLITE_FILE_DIRECTORY = os.environ.get(
    "SQLITE_FILE_DIRECTORY", os.path.dirname(data.__file__)
).strip()

# Debug logging configuration

DEBUG_LOG_TO_CONSOLE = os.environ.get("DEBUG_LOG_TO_CONSOLE", None)
"""
Enable console logging output. Set to any value to enable.
Example: DEBUG_LOG_TO_CONSOLE=1
"""

DEBUG_LOG_TO_FILE = os.environ.get("DEBUG_LOG_TO_FILE", None)
"""
Enable file logging. Set to file path to enable.
Example: DEBUG_LOG_TO_FILE=logs/debug.log
"""

DEBUG_LOG_TO_DB = os.environ.get("DEBUG_LOG_TO_DB", None)
"""
Enable database logging. Set to any value to enable.
Example: DEBUG_LOG_TO_DB=1
"""

# Mock models (for testing/development to save API costs)
USE_MOCK_MODEL = os.environ.get("USE_MOCK_MODEL", "false").strip().lower() in (
    "true",
    "1",
    "yes",
)
