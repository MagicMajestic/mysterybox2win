import logging
import os
import time
import asyncio
import discord
import dotenv
from bot import MysteryBoxBot

# Load environment variables from .env file
dotenv.load_dotenv()

# Configure logging
def setup_logging():
    """Setup logging to both console and file"""
    # Ensure logs directory exists
    os.makedirs('logs', exist_ok=True)
    
    # Create console handler with INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_format)
    
    # Create file handler with DEBUG level
    log_file = 'logs/bot.log'
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_format)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Add handlers
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
    
    return root_logger

logger = setup_logging()
logger.info(f"Starting bot with Discord.py version: {discord.__version__}")
logger.info(f"Debug mode: {os.getenv('DEBUG_MODE', 'false').lower() == 'true'}")
logger.info(f"Command sync: {os.getenv('SYNC_COMMANDS', 'false').lower() == 'true'}")

# Maximum number of reconnection attempts
MAX_RETRIES = 10  # Увеличиваем количество попыток
# Initial time to wait between retries in seconds
INITIAL_RETRY_INTERVAL = 5
# Maximum time to wait between retries in seconds
MAX_RETRY_INTERVAL = 900  # 15 minutes max delay
# Exponential backoff multiplier
BACKOFF_MULTIPLIER = 1.5

async def run_bot_with_retry(token):
    """Runs the bot with automatic retry on failure"""
    retry_count = 0
    retry_interval = INITIAL_RETRY_INTERVAL
    total_retry_attempt = 0
    
    # Track rate limit buckets
    rate_limit_reset = 0
    
    while retry_count < MAX_RETRIES:
        try:
            # Log attempt information
            logger.info(f"Starting bot (attempt {retry_count + 1}/{MAX_RETRIES}, total attempts: {total_retry_attempt + 1})")
            total_retry_attempt += 1
            
            # Initialize the bot with a new instance each time
            bot = MysteryBoxBot()
            
            # Use run_until_complete for better control
            logger.info("Bot connecting to Discord...")
            await bot.start(token)
            
            # If we get here, the bot exited normally
            logger.info("Bot disconnected normally")
            return
        except discord.errors.HTTPException as e:
            if e.status == 429:  # Rate limited
                retry_after = e.retry_after if hasattr(e, 'retry_after') else retry_interval
                current_time = time.time()
                
                if current_time < rate_limit_reset:
                    # We're still in cooldown, wait longer
                    retry_after = max(retry_after, rate_limit_reset - current_time)
                
                rate_limit_reset = current_time + retry_after
                logger.warning(f"Rate limited by Discord API. Waiting {retry_after:.1f} seconds...")
                await asyncio.sleep(retry_after)
                retry_interval = min(retry_interval * BACKOFF_MULTIPLIER, MAX_RETRY_INTERVAL)
                continue  # Skip incrementing retry count for rate limits
            elif e.status == 400 and "The request body contains invalid JSON." in str(e):
                logger.error(f"Invalid JSON in request: {e}")
                # Увеличиваем задержку для подобных ошибок
                retry_interval = min(retry_interval * 3, MAX_RETRY_INTERVAL)
            elif e.status == 500 or e.status == 502 or e.status == 503 or e.status == 504:
                # Серверные ошибки Discord - просто пробуем еще раз
                logger.error(f"Discord server error (HTTP {e.status}): {e}")
            else:
                logger.error(f"HTTP error (status {e.status}): {e}")
        except discord.errors.LoginFailure as e:
            logger.error(f"Invalid token or login failure: {e}")
            return  # Don't retry on auth errors
        except discord.errors.GatewayNotFound as e:
            logger.error(f"Gateway error: {e}")
            # Discord API недоступен, ждем дольше
            retry_interval = min(retry_interval * 2, MAX_RETRY_INTERVAL)
        except discord.errors.ConnectionClosed as e:
            logger.error(f"Connection closed: {e}")
            # Небольшая дополнительная задержка
            retry_interval = min(retry_interval * 1.5, MAX_RETRY_INTERVAL)
        except ConnectionResetError as e:
            logger.error(f"Connection reset: {e}")
        except asyncio.exceptions.TimeoutError as e:
            logger.error(f"Connection timeout: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
        
        # Increment retry count and wait before next attempt
        retry_count += 1
        if retry_count < MAX_RETRIES:
            logger.info(f"Retrying in {retry_interval} seconds... (Attempt {retry_count}/{MAX_RETRIES})")
            await asyncio.sleep(retry_interval)
            # Exponential backoff, capped at MAX_RETRY_INTERVAL
            retry_interval = min(retry_interval * 2, MAX_RETRY_INTERVAL)
        else:
            logger.error(f"Failed to start bot after {MAX_RETRIES} attempts")

def main():
    # Get token from environment variables
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        logger.error("No Discord token found. Please set the DISCORD_TOKEN environment variable.")
        return
    
    # Only sync commands on demand through the SYNC_COMMANDS environment variable
    sync_commands = os.getenv("SYNC_COMMANDS", "false").lower()
    if sync_commands == "true":
        logger.info("Command sync is enabled for this session")
    
    # Run bot with retry mechanism
    try:
        asyncio.run(run_bot_with_retry(token))
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
