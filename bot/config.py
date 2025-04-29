import os
from pathlib import Path
from dotenv import load_dotenv
import yaml

# Load environment variables from .env file
load_dotenv()

config_dir = Path(__file__).parent.parent.resolve() / "config"

# Load chat modes from YAML (keeping this as YAML for simplicity)
with open(config_dir / "chat_modes.yml", 'r') as f:
    chat_modes = yaml.safe_load(f)

# Get configuration from environment variables
telegram_token = os.getenv("TELEGRAM_TOKEN")
gemini_api_key = os.getenv("GEMINI_API_KEY")

# Admin username for premium subscription
admin_username = os.getenv("ADMIN_USERNAME", "admin_username")  # Default value if not set

# Parse allowed usernames from comma-separated string
allowed_telegram_usernames_str = os.getenv("ALLOWED_TELEGRAM_USERNAMES", "")
allowed_telegram_usernames = [username.strip() for username in allowed_telegram_usernames_str.split(",") if username.strip()]

# Default language settings
DEFAULT_LANGUAGE = "Uzbek"  # Set Uzbek as default language
