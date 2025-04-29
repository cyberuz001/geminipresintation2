#!/usr/bin/env python3
import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add the project root directory to Python path
project_root = Path(__file__).parent.resolve()
sys.path.append(str(project_root))

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def main():
    """Main entry point for the application"""
    # Load environment variables
    load_dotenv()
    
    # Check if required environment variables are set
    required_vars = ["TELEGRAM_TOKEN", "GEMINI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        logger.error("Please create a .env file based on .env.example and fill in the required values.")
        return 1
    
    # Print Gemini API key (first few characters) for debugging
    gemini_api_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_api_key:
        masked_key = gemini_api_key[:4] + "*" * (len(gemini_api_key) - 8) + gemini_api_key[-4:] if len(gemini_api_key) > 8 else "***"
        logger.info(f"Using Gemini API key: {masked_key}")
    else:
        logger.warning("Gemini API key is not set or empty")
    
    # Import the bot module
    try:
        from bot.bot import run_bot
        logger.info("Starting the bot...")
        run_bot()
        return 0
    except ImportError as e:
        logger.error(f"Failed to import bot module: {e}")
        logger.error("Make sure all dependencies are installed: pip install -r requirements.txt")
        return 1
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Error running the bot: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
