import discord
from discord.ext import commands
import os
import logging
import asyncio
import dotenv
from utils.database import ensure_data_directory

# Load environment variables from .env file
dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# ID серверов, на которых разрешена работа бота
ALLOWED_GUILD_IDS = [
    714813888226525226,  # Основной сервер
    1093641722589876336   # Тестовый сервер
]

class MysteryBoxBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix="/",
            intents=intents,
            application_id=os.getenv("APPLICATION_ID"),
            help_command=None
        )
        
        # Ensure data directory exists
        ensure_data_directory()
        
        # Store active giveaways and their tasks
        self.active_giveaways = {}
        
    async def setup_hook(self):
        # Load cogs
        await self.load_extension("cogs.giveaway")
        logger.info("Giveaway cog loaded")
        
        # Initialize session storage
        self._sessions = set()
        
    def store_session(self, session):
        """Store session reference for cleanup"""
        self._sessions.add(session)
        
    def remove_session(self, session):
        """Remove session reference"""
        self._sessions.discard(session)
        
    async def close(self):
        """Cleanup when bot is shutting down"""
        # Close all active sessions
        for session in self._sessions:
            try:
                await session.close()
            except:
                pass
        self._sessions.clear()
        
        # Call parent close
        await super().close()
        
        # Sync commands only if needed (using environment variable)
        should_sync = os.getenv("SYNC_COMMANDS", "false").lower() == "true"
        if should_sync:
            try:
                logger.info("Syncing command tree with Discord...")
                await self.tree.sync()
                logger.info("Command tree successfully synced")
            except discord.HTTPException as e:
                logger.error(f"Failed to sync commands: {e}")
        else:
            logger.info("Skipping command sync (set SYNC_COMMANDS=true to force sync)")
    
    async def on_ready(self):
        logger.info(f"Logged in as {self.user.name} ({self.user.id})")
        logger.info("Bot is ready!")
        
        # Проверяем режим отладки
        debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
        if debug_mode:
            logger.warning("⚠️ WARNING: DEBUG MODE ENABLED - Server whitelist restrictions are disabled ⚠️")
            logger.warning("⚠️ This should only be used during development/testing, not in production ⚠️")
        else:
            logger.info("Production mode active - Server whitelist restrictions are enforced")
        
        # Set bot activity
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.playing,
                name="MysteryBox Giveaways"
            )
        )
        
        # Проверка текущих серверов
        guild_count = len(self.guilds)
        logger.info(f"Bot is present on {guild_count} server(s)")
        
        allowed_count = 0
        unauthorized_count = 0
        
        # Проверка и покидание неразрешенных серверов при запуске
        for guild in self.guilds:
            if guild.id in ALLOWED_GUILD_IDS:
                allowed_count += 1
                logger.info(f"Authorized server: {guild.name} (ID: {guild.id})")
            else:
                unauthorized_count += 1
                if not debug_mode:
                    logger.warning(f"⚠️ Unauthorized server detected: {guild.name} (ID: {guild.id}). Leaving server.")
                    try:
                        await guild.leave()
                        logger.info(f"Successfully left unauthorized server: {guild.name}")
                    except Exception as e:
                        logger.error(f"Error leaving unauthorized server {guild.name}: {e}")
                else:
                    logger.warning(f"⚠️ Unauthorized server detected (in debug mode): {guild.name} (ID: {guild.id})")
        
        # Итоговая статистика
        if not debug_mode:
            logger.info(f"Servers summary: {allowed_count} authorized, {unauthorized_count} unauthorized (left)")
        else:
            logger.warning(f"Servers summary (debug mode): {allowed_count} authorized, {unauthorized_count} unauthorized (not left due to debug mode)")
                
    async def on_guild_join(self, guild):
        """Обработка события присоединения к новому серверу"""
        # Проверяем режим отладки
        debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
        
        if guild.id in ALLOWED_GUILD_IDS:
            logger.info(f"Bot was added to authorized server: {guild.name} (ID: {guild.id})")
            # Отправить уведомление о добавлении бота
            system_channel = guild.system_channel
            if system_channel and system_channel.permissions_for(guild.me).send_messages:
                try:
                    embed = discord.Embed(
                        title="MysteryBox Bot добавлен на сервер!",
                        description="Привет! Я бот для проведения розыгрышей с таинственными призами. "
                                    "Только администраторы могут управлять розыгрышами. "
                                    "Чтобы создать розыгрыш, используйте команду `/mysterybox`.",
                        color=discord.Color.blue()
                    )
                    await system_channel.send(embed=embed)
                except Exception as e:
                    logger.error(f"Error sending welcome message: {e}")
            return
        
        # Если сервер не в белом списке
        if not debug_mode:
            logger.warning(f"⚠️ Bot was added to unauthorized server: {guild.name} (ID: {guild.id}). Leaving server.")
            try:
                # Отправить сообщение перед выходом, если возможно
                system_channel = guild.system_channel
                if system_channel and system_channel.permissions_for(guild.me).send_messages:
                    try:
                        embed = discord.Embed(
                            title="MysteryBox Bot не доступен на этом сервере",
                            description="Извините, но этот бот доступен только на определенных серверах. "
                                        "Если вы хотите использовать бота, пожалуйста, свяжитесь с его владельцем для получения разрешения.",
                            color=discord.Color.red()
                        )
                        await system_channel.send(embed=embed)
                    except Exception as e:
                        logger.error(f"Error sending unauthorized message: {e}")
                
                # Покидаем сервер
                await guild.leave()
                logger.info(f"Successfully left unauthorized server: {guild.name}")
            except Exception as e:
                logger.error(f"Error leaving unauthorized server {guild.name}: {e}")
        else:
            logger.warning(f"⚠️ Bot was added to unauthorized server (in debug mode): {guild.name} (ID: {guild.id})")
            logger.warning("⚠️ Debug mode is enabled, so the bot will remain on this server, but this behavior is not recommended for production")
        
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("У вас недостаточно прав для выполнения этой команды.")
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            logger.error(f"Command error: {error}")
            await ctx.send(f"Произошла ошибка: {error}")
