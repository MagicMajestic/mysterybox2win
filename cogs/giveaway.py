import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
import random
import logging
from datetime import datetime, timedelta
import traceback
from utils.database import (
    load_giveaways,
    save_giveaways,
    load_prizes,
    save_prizes,
    load_gifs,
    save_gifs,
    save_gif_file,
    get_gif_path,
    load_prize_lists,
    save_prize_lists,
    save_prize_list_file,
    load_prize_list_file,
    parse_prize_ids,
    GIVEAWAYS_FILE,
    PRIZES_FILE,
    GIFS_FILE,
    IMAGES_DIR,
    PRIZE_LISTS_DIR,
    PRIZE_LISTS_FILE
)

logger = logging.getLogger(__name__)

class GiveawayButton(discord.ui.View):
    def __init__(self, giveaway_id, timeout=None):
        super().__init__(timeout=timeout)
        self.giveaway_id = giveaway_id
        
    @discord.ui.button(label="Учавствовать", style=discord.ButtonStyle.primary, emoji="🎁")
    async def participate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Get the cog instance
        giveaway_cog = interaction.client.get_cog("GiveawayCog")
        
        if giveaway_cog:
            await giveaway_cog.add_participant(interaction, self.giveaway_id)
        else:
            await interaction.response.send_message("Система розыгрышей не доступна в данный момент.", ephemeral=True)

class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.giveaways = load_giveaways()
        self.prizes = load_prizes()
        self.gifs = load_gifs()
        self.prize_lists = load_prize_lists()
        # ID серверов, на которых разрешена работа бота
        self.allowed_guild_ids = [
            714813888226525226,  # Основной сервер
            1093641722589876336   # Тестовый сервер
        ]
        # Режим отладки - если True, проверка сервера отключена
        # В продакшене режим должен быть отключен (false)
        self.debug_mode = os.getenv("DEBUG_MODE", "false").lower() == "true"
        logger.info(f"Debug mode: {'ENABLED' if self.debug_mode else 'DISABLED'}")
        
        # Проверяем, активирован ли безопасный режим для предотвращения использования на других серверах
        if not self.debug_mode:
            logger.warning("PRODUCTION MODE ENABLED - Bot will only work on whitelisted servers")
        
        self.reload_active_giveaways()
        
    async def is_allowed_guild(self, interaction: discord.Interaction) -> bool:
        """Проверяет, разрешен ли сервер для использования бота"""
        # Если включен режим отладки, пропускаем проверку сервера
        if self.debug_mode:
            return True
            
        guild_id = interaction.guild_id
        if guild_id not in self.allowed_guild_ids:
            await interaction.response.send_message(
                "Этот бот доступен только на определенных серверах. Свяжитесь с владельцем бота для получения доступа.",
                ephemeral=True
            )
            return False
        return True
        
    async def is_admin(self, interaction: discord.Interaction) -> bool:
        """Проверяет, имеет ли пользователь права администратора"""
        debug_prefix = "[DEBUG]" if self.debug_mode else "[PROD]"
        logger.debug(f"{debug_prefix} Checking admin for user {interaction.user.name} (ID: {interaction.user.id})")
        
        # Проверка на разрешенный сервер перед всеми проверками
        if not await self.is_allowed_guild(interaction):
            logger.warning(f"{debug_prefix} Server not allowed: {interaction.guild_id}")
            return False
        
        # В режиме отладки, если установлен DEBUG_MODE=true
        if self.debug_mode:
            logger.warning(f"{debug_prefix} Debug mode enabled, bypassing admin check for: {interaction.user.name}")
            return True
        
        try:
            # Сохраняем подробный лог для отладки
            guild = interaction.guild
            if guild:
                logger.debug(f"{debug_prefix} Guild: {guild.name} (ID: {guild.id})")
                logger.debug(f"{debug_prefix} Owner ID: {guild.owner_id}")
                logger.debug(f"{debug_prefix} User ID: {interaction.user.id}")
                
                # Проверка на владельца сервера - всегда разрешать владельцу
                if guild.owner_id == interaction.user.id:
                    logger.info(f"{debug_prefix} User is server owner, granting access")
                    return True
                
                # Получаем объект member для более детальной проверки прав
                member = guild.get_member(interaction.user.id)
                if member is None:
                    try:
                        logger.debug(f"{debug_prefix} Member not found via get_member, trying fetch_member")
                        member = await guild.fetch_member(interaction.user.id)
                    except Exception as e:
                        logger.error(f"{debug_prefix} Error fetching member: {e}")
                
                # Проверяем права администратора через объект member, если он доступен
                if member:
                    # Проверка, есть ли роль с правами администратора
                    has_admin_role = False
                    admin_role_names = []
                    
                    for role in member.roles:
                        if role.permissions.administrator:
                            has_admin_role = True
                            admin_role_names.append(role.name)
                    
                    if has_admin_role:
                        logger.info(f"{debug_prefix} User has admin role(s): {', '.join(admin_role_names)}")
                        return True
                    
                    # Проверка через guild_permissions
                    if member.guild_permissions.administrator:
                        logger.info(f"{debug_prefix} User has administrator permission")
                        return True
                
                # Если не удалось проверить через member, используем guild_permissions из interaction
                if interaction.user.guild_permissions.administrator:
                    logger.info(f"{debug_prefix} User has administrator permission via interaction check")
                    return True
                
                # Если дошли сюда - пользователь не имеет прав администратора
                logger.warning(f"{debug_prefix} User does not have administrator permissions")
                await interaction.response.send_message(
                    "У вас нет прав администратора для использования этой команды. "
                    "Необходимы права администратора или соответствующая роль.",
                    ephemeral=True
                )
                return False
            else:
                logger.error(f"{debug_prefix} Guild object is None for interaction")
                await interaction.response.send_message(
                    "Произошла ошибка при проверке ваших прав. Пожалуйста, попробуйте позже.",
                    ephemeral=True
                )
                return False
                
        except Exception as e:
            logger.error(f"{debug_prefix} Error in admin permission check: {str(e)}")
            logger.error(traceback.format_exc())
            
            # В случае ошибки разрешаем только в режиме отладки
            if self.debug_mode:
                logger.warning(f"{debug_prefix} Allowing access in debug mode despite error")
                return True
            
            # В продакшене блокируем при ошибках
            await interaction.response.send_message(
                "Произошла ошибка при проверке ваших прав администратора. "
                "Пожалуйста, попробуйте позже или свяжитесь с владельцем бота.",
                ephemeral=True
            )
            return False
        
    def reload_active_giveaways(self):
        """Restart timers for any active giveaways when bot starts/restarts"""
        now = datetime.now().timestamp()
        
        for giveaway_id, giveaway in list(self.giveaways.items()):
            if giveaway.get("ended", False):
                continue
                
            end_time = giveaway.get("end_time", 0)
            
            if end_time > now:
                # Recreate the task for this giveaway
                seconds_left = end_time - now
                self.bot.active_giveaways[giveaway_id] = asyncio.create_task(
                    self.schedule_giveaway_end(giveaway_id, seconds_left)
                )
                logger.info(f"Restored giveaway {giveaway_id} with {seconds_left:.2f} seconds left")
            else:
                # This giveaway should have ended already
                asyncio.create_task(self.end_giveaway(giveaway_id))
                logger.info(f"Ending missed giveaway {giveaway_id}")
    
    async def schedule_giveaway_end(self, giveaway_id, seconds):
        """Schedule the end of a giveaway after the specified time"""
        try:
            await asyncio.sleep(seconds)
            await self.end_giveaway(giveaway_id)
        except asyncio.CancelledError:
            logger.info(f"Giveaway task for {giveaway_id} was cancelled")
        except Exception as e:
            logger.error(f"Error in giveaway task: {e}")
            logger.error(traceback.format_exc())
    
    async def end_giveaway(self, giveaway_id):
        """End a giveaway and select a winner"""
        try:
            if giveaway_id not in self.giveaways:
                logger.error(f"Giveaway {giveaway_id} not found when trying to end it")
                return
                
            giveaway = self.giveaways[giveaway_id]
            
            # Mark as ended
            giveaway["ended"] = True
            save_giveaways(self.giveaways)
            
            channel_id = giveaway.get("channel_id")
            message_id = giveaway.get("message_id")
            participants = giveaway.get("participants", [])
            
            if not channel_id or not message_id:
                logger.error(f"Missing channel_id or message_id for giveaway {giveaway_id}")
                return
                
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                logger.error(f"Could not find channel {channel_id} for giveaway {giveaway_id}")
                return
            
            try:
                message = await channel.fetch_message(int(message_id))
            except discord.NotFound:
                logger.error(f"Could not find message {message_id} in channel {channel_id}")
                message = None
            
            # Select winner if there are participants
            if participants:
                winner_id = random.choice(participants)
                
                # Select a random prize
                prize = "Mystery Prize"  # Default if no prizes available
                
                # Check if the giveaway has assigned prizes
                if giveaway.get("assigned_prizes"):
                    prize = random.choice(list(giveaway["assigned_prizes"].values()))
                # Otherwise use the global prize pool
                elif self.prizes:
                    prize = random.choice(list(self.prizes.values()))
                
                winner_mention = f"<@{winner_id}>"
                
                # Send the winner announcement
                embed = discord.Embed(
                    title="🎉 Розыгрыш завершен! 🎉",
                    description=f"**Победитель: {winner_mention}**\n**Приз: {prize}**",
                    color=discord.Color.green()
                )
                embed.set_footer(text=f"Розыгрыш ID: {giveaway_id}")
                
                # Check if there's a celebration GIF attached to this giveaway
                gif_id = giveaway.get("celebration_gif")
                if gif_id and gif_id in self.gifs:
                    gif_path = get_gif_path(gif_id)
                    if gif_path and os.path.exists(gif_path):
                        file = discord.File(gif_path, filename="celebration.gif")
                        embed.set_image(url="attachment://celebration.gif")
                        await channel.send(
                            content=f"Поздравляем {winner_mention}! Вы выиграли **{prize}**!",
                            embed=embed,
                            file=file
                        )
                    else:
                        await channel.send(
                            content=f"Поздравляем {winner_mention}! Вы выиграли **{prize}**!",
                            embed=embed
                        )
                else:
                    await channel.send(
                        content=f"Поздравляем {winner_mention}! Вы выиграли **{prize}**!",
                        embed=embed
                    )
                
                # Update the original message if it exists
                if message:
                    original_embed = message.embeds[0] if message.embeds else None
                    if original_embed:
                        original_embed.title = "🎁 Розыгрыш завершен!"
                        original_embed.description += f"\n\n**Победитель: {winner_mention}**\n**Приз: {prize}**"
                        original_embed.color = discord.Color.dark_grey()
                        
                        await message.edit(embed=original_embed, view=None)
            else:
                # No participants
                embed = discord.Embed(
                    title="🎁 Розыгрыш завершен!",
                    description="К сожалению, никто не принял участие в розыгрыше.",
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"Розыгрыш ID: {giveaway_id}")
                
                await channel.send(embed=embed)
                
                # Update the original message if it exists
                if message:
                    original_embed = message.embeds[0] if message.embeds else None
                    if original_embed:
                        original_embed.title = "🎁 Розыгрыш завершен!"
                        original_embed.description += "\n\nК сожалению, никто не принял участие в розыгрыше."
                        original_embed.color = discord.Color.red()
                        
                        await message.edit(embed=original_embed, view=None)
            
            # Clean up
            if giveaway_id in self.bot.active_giveaways:
                del self.bot.active_giveaways[giveaway_id]
                
        except Exception as e:
            logger.error(f"Error ending giveaway {giveaway_id}: {e}")
            logger.error(traceback.format_exc())
    
    @app_commands.command(name="mysterybox", description="Создать новый розыгрыш")
    @app_commands.describe(
        hours="Продолжительность розыгрыша в часах",
        minutes="Продолжительность розыгрыша в минутах (добавляется к часам)",
        title="Название розыгрыша",
        description="Описание розыгрыша"
    )
    @app_commands.default_permissions(administrator=True)
    async def create_giveaway(
        self, 
        interaction: discord.Interaction, 
        hours: int = 24, 
        minutes: int = 0,
        title: str = "Таинственный розыгрыш",
        description: str = "Нажмите на кнопку ниже, чтобы принять участие в розыгрыше!"
    ):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
            
        # Generate unique ID for the giveaway
        giveaway_id = f"{interaction.guild.id}-{datetime.now().timestamp()}"
        
        # Calculate end time
        duration = timedelta(hours=hours, minutes=minutes)
        end_time = datetime.now() + duration
        end_timestamp = end_time.timestamp()
        
        # Create embed
        embed = discord.Embed(
            title=f"🎁 {title}",
            description=f"{description}\n\n**Окончание:** <t:{int(end_timestamp)}:R>",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"ID розыгрыша: {giveaway_id}")
        
        # Create the view with the button
        view = GiveawayButton(giveaway_id)
        
        # Respond to the interaction
        await interaction.response.send_message("Розыгрыш создан!", ephemeral=True)
        
        # Send the giveaway message
        channel = interaction.channel
        giveaway_message = await channel.send(embed=embed, view=view)
        
        # Save giveaway data
        self.giveaways[giveaway_id] = {
            "title": title,
            "description": description,
            "creator_id": str(interaction.user.id),
            "channel_id": str(channel.id),
            "message_id": str(giveaway_message.id),
            "guild_id": str(interaction.guild.id),
            "end_time": end_timestamp,
            "participants": [],
            "ended": False
        }
        save_giveaways(self.giveaways)
        
        # Schedule the giveaway end
        seconds_until_end = duration.total_seconds()
        self.bot.active_giveaways[giveaway_id] = asyncio.create_task(
            self.schedule_giveaway_end(giveaway_id, seconds_until_end)
        )
        
        logger.info(f"Created giveaway {giveaway_id} ending in {seconds_until_end} seconds")
    
    async def add_participant(self, interaction: discord.Interaction, giveaway_id: str):
        """Add a participant to a giveaway"""
        # В режиме отладки выводим информацию
        if self.debug_mode:
            print(f"Debug: Adding participant to giveaway {giveaway_id}")
            print(f"Debug: User: {interaction.user.name} (ID: {interaction.user.id})")
            print(f"Debug: Guild: {interaction.guild.name} (ID: {interaction.guild.id})")
            
        # В режиме отладки пропускаем проверку сервера
        if not self.debug_mode:
            # Проверяем, что это разрешенный сервер
            if not await self.is_allowed_guild(interaction):
                print(f"Debug: Server not allowed, participation blocked")
                return
        else:
            print(f"Debug: Skipping server check in debug mode")
            
        if giveaway_id not in self.giveaways:
            print(f"Debug: Giveaway {giveaway_id} not found")
            await interaction.response.send_message("Этот розыгрыш больше не активен.", ephemeral=True)
            return
            
        giveaway = self.giveaways[giveaway_id]
        print(f"Debug: Giveaway info: {giveaway['title']}, ended: {giveaway.get('ended', False)}")
        
        if giveaway.get("ended", False):
            print(f"Debug: Giveaway already ended")
            await interaction.response.send_message("Этот розыгрыш уже завершен.", ephemeral=True)
            return
            
        user_id = str(interaction.user.id)
        participants = giveaway.get("participants", [])
        print(f"Debug: Current participants: {len(participants)}")
        
        if user_id in participants:
            print(f"Debug: User already participating")
            await interaction.response.send_message("Вы уже участвуете в этом розыгрыше!", ephemeral=True)
            return
            
        # Add user to participants
        participants.append(user_id)
        giveaway["participants"] = participants
        save_giveaways(self.giveaways)
        print(f"Debug: User added to participants, new count: {len(participants)}")
        
        await interaction.response.send_message("Вы успешно присоединились к розыгрышу! Ожидайте результатов.", ephemeral=True)
        logger.info(f"User {user_id} joined giveaway {giveaway_id}")
    
    @app_commands.command(name="participants", description="Посмотреть список участников розыгрыша")
    @app_commands.describe(giveaway_id="ID розыгрыша (можно найти в нижней части сообщения с розыгрышем)")
    @app_commands.default_permissions(administrator=True)
    async def view_participants(self, interaction: discord.Interaction, giveaway_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
            
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Розыгрыш с указанным ID не найден.", ephemeral=True)
            return
            
        giveaway = self.giveaways[giveaway_id]
        participants = giveaway.get("participants", [])
        
        if not participants:
            await interaction.response.send_message("В этом розыгрыше пока нет участников.", ephemeral=True)
            return
            
        # Fetch user names
        participant_list = []
        for user_id in participants:
            try:
                user = await self.bot.fetch_user(int(user_id))
                participant_list.append(f"{user.name} ({user.mention})")
            except:
                participant_list.append(f"Пользователь с ID {user_id}")
        
        # Create paginated embeds if needed
        embed = discord.Embed(
            title=f"Участники розыгрыша",
            description=f"**Название:** {giveaway['title']}\n**Всего участников:** {len(participants)}",
            color=discord.Color.blue()
        )
        
        # Add participants list (limited to 25 per embed to avoid hitting the character limit)
        for i in range(0, len(participant_list), 25):
            chunk = participant_list[i:i+25]
            embed.add_field(
                name=f"Участники {i+1}-{i+len(chunk)}",
                value="\n".join(chunk),
                inline=False
            )
        
        embed.set_footer(text=f"ID розыгрыша: {giveaway_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="addprize", description="Добавить приз в список возможных призов")
    @app_commands.describe(
        prize_id="Уникальный идентификатор приза",
        prize_name="Название приза"
    )
    @app_commands.default_permissions(administrator=True)
    async def add_prize(self, interaction: discord.Interaction, prize_id: str, prize_name: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
            
        if prize_id in self.prizes:
            await interaction.response.send_message("Приз с таким ID уже существует. Используйте другой ID.", ephemeral=True)
            return
            
        # Add the prize
        self.prizes[prize_id] = prize_name
        save_prizes(self.prizes)
        
        await interaction.response.send_message(f"Приз **{prize_name}** успешно добавлен в список призов.", ephemeral=True)
        logger.info(f"Added prize {prize_id}: {prize_name}")
    
    @app_commands.command(name="removeprize", description="Удалить приз из списка возможных призов")
    @app_commands.describe(prize_id="ID приза для удаления")
    @app_commands.default_permissions(administrator=True)
    async def remove_prize(self, interaction: discord.Interaction, prize_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
            
        if prize_id not in self.prizes:
            await interaction.response.send_message("Приз с указанным ID не найден.", ephemeral=True)
            return
            
        # Remove the prize
        prize_name = self.prizes.pop(prize_id)
        save_prizes(self.prizes)
        
        await interaction.response.send_message(f"Приз **{prize_name}** успешно удален из списка призов.", ephemeral=True)
        logger.info(f"Removed prize {prize_id}: {prize_name}")
    
    @app_commands.command(name="listprizes", description="Посмотреть список возможных призов")
    @app_commands.default_permissions(administrator=True)
    async def list_prizes(self, interaction: discord.Interaction):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
            
        if not self.prizes:
            await interaction.response.send_message("Список призов пуст.", ephemeral=True)
            return
            
        # Create an embed with the list of prizes
        embed = discord.Embed(
            title="Список призов",
            description="Все возможные призы для розыгрышей:",
            color=discord.Color.gold()
        )
        
        for prize_id, prize_name in self.prizes.items():
            embed.add_field(
                name=prize_id,
                value=prize_name,
                inline=True
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @app_commands.command(name="endgiveaway", description="Досрочно завершить розыгрыш и выбрать победителя")
    @app_commands.describe(giveaway_id="ID розыгрыша для завершения")
    @app_commands.default_permissions(administrator=True)
    async def end_giveaway_command(self, interaction: discord.Interaction, giveaway_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
            
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Розыгрыш с указанным ID не найден.", ephemeral=True)
            return
            
        giveaway = self.giveaways[giveaway_id]
        
        if giveaway.get("ended", False):
            await interaction.response.send_message("Этот розыгрыш уже завершен.", ephemeral=True)
            return
        
        # Cancel the scheduled task
        if giveaway_id in self.bot.active_giveaways:
            self.bot.active_giveaways[giveaway_id].cancel()
        
        await interaction.response.send_message("Розыгрыш завершается досрочно...", ephemeral=True)
        
        # End the giveaway and select a winner
        await self.end_giveaway(giveaway_id)
        
    @app_commands.command(name="cancelgiveaway", description="Отменить активный розыгрыш")
    @app_commands.describe(giveaway_id="ID розыгрыша для отмены")
    @app_commands.default_permissions(administrator=True)
    async def cancel_giveaway(self, interaction: discord.Interaction, giveaway_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
            
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Розыгрыш с указанным ID не найден.", ephemeral=True)
            return
            
        giveaway = self.giveaways[giveaway_id]
        
        if giveaway.get("ended", False):
            await interaction.response.send_message("Этот розыгрыш уже завершен.", ephemeral=True)
            return
            
        # Cancel the scheduled task if it exists
        if giveaway_id in self.bot.active_giveaways:
            self.bot.active_giveaways[giveaway_id].cancel()
            del self.bot.active_giveaways[giveaway_id]
        
        # Mark as ended
        giveaway["ended"] = True
        save_giveaways(self.giveaways)
        
        # Try to update the message
        try:
            channel = self.bot.get_channel(int(giveaway["channel_id"]))
            if channel:
                message = await channel.fetch_message(int(giveaway["message_id"]))
                if message:
                    original_embed = message.embeds[0] if message.embeds else None
                    if original_embed:
                        original_embed.title = "🎁 Розыгрыш отменен!"
                        original_embed.description += "\n\nЭтот розыгрыш был отменен администратором."
                        original_embed.color = discord.Color.red()
                        
                        await message.edit(embed=original_embed, view=None)
        except Exception as e:
            logger.error(f"Error updating cancelled giveaway message: {e}")
        
        await interaction.response.send_message(f"Розыгрыш успешно отменен.", ephemeral=True)
        logger.info(f"Cancelled giveaway {giveaway_id}")

    @app_commands.command(name="setexacttime", description="Установить точное время окончания розыгрыша")
    @app_commands.describe(
        giveaway_id="ID розыгрыша",
        date="Дата в формате ДД.ММ.ГГГГ, например, 25.12.2025",
        time="Время в формате ЧЧ:ММ, например, 18:30"
    )
    @app_commands.default_permissions(administrator=True)
    async def set_exact_time(self, interaction: discord.Interaction, giveaway_id: str, date: str, time: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Validate giveaway ID
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Розыгрыш с указанным ID не найден.", ephemeral=True)
            return
        
        giveaway = self.giveaways[giveaway_id]
        
        if giveaway.get("ended", False):
            await interaction.response.send_message("Невозможно изменить время для завершенного розыгрыша.", ephemeral=True)
            return
        
        # Parse the date and time
        try:
            day, month, year = map(int, date.split('.'))
            hour, minute = map(int, time.split(':'))
            
            end_time = datetime(year, month, day, hour, minute)
            now = datetime.now()
            
            if end_time <= now:
                await interaction.response.send_message("Время окончания должно быть в будущем.", ephemeral=True)
                return
            
            end_timestamp = end_time.timestamp()
            seconds_until_end = end_timestamp - now.timestamp()
            
            # Cancel any existing task
            if giveaway_id in self.bot.active_giveaways:
                self.bot.active_giveaways[giveaway_id].cancel()
            
            # Update the giveaway end time
            giveaway["end_time"] = end_timestamp
            save_giveaways(self.giveaways)
            
            # Reschedule the end task
            self.bot.active_giveaways[giveaway_id] = asyncio.create_task(
                self.schedule_giveaway_end(giveaway_id, seconds_until_end)
            )
            
            # Update the original message
            try:
                channel = self.bot.get_channel(int(giveaway.get("channel_id", 0)))
                message_id = int(giveaway.get("message_id", 0))
                
                if channel and message_id:
                    message = await channel.fetch_message(message_id)
                    if message:
                        original_embed = message.embeds[0] if message.embeds else None
                        if original_embed:
                            # Update the end time in the description
                            description_parts = original_embed.description.split("**Окончание:**")
                            if len(description_parts) > 1:
                                new_description = description_parts[0] + f"**Окончание:** <t:{int(end_timestamp)}:R>"
                                original_embed.description = new_description
                                
                                await message.edit(embed=original_embed)
            except Exception as e:
                logger.error(f"Error updating message with new end time: {e}")
            
            await interaction.response.send_message(
                f"Время окончания розыгрыша изменено на {date} {time}.",
                ephemeral=True
            )
            logger.info(f"Updated end time for giveaway {giveaway_id} to {end_time}")
        except ValueError:
            await interaction.response.send_message(
                "Неверный формат даты или времени. Используйте ДД.ММ.ГГГГ для даты и ЧЧ:ММ для времени.",
                ephemeral=True
            )
        except Exception as e:
            logger.error(f"Error setting exact time: {e}")
            await interaction.response.send_message(
                f"Произошла ошибка при установке времени: {str(e)}",
                ephemeral=True
            )
            
    @app_commands.command(name="uploadgif", description="Загрузить GIF-анимацию для поздравления победителя")
    @app_commands.describe(
        gif_id="Уникальный идентификатор для GIF-анимации",
        gif_name="Название анимации для отображения в списке"
    )
    @app_commands.default_permissions(administrator=True)
    async def upload_gif(self, interaction: discord.Interaction, gif_id: str, gif_name: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Check if GIF ID already exists
        if gif_id in self.gifs:
            await interaction.response.send_message("GIF-анимация с таким ID уже существует. Используйте другой ID.", ephemeral=True)
            return
        
        # Send initial response
        await interaction.response.send_message(
            "Пожалуйста, прикрепите GIF-анимацию в формате 1:1 в следующем сообщении.",
            ephemeral=True
        )
        
        # Define a check for the attachment in the follow-up message
        def check(message):
            return (message.author.id == interaction.user.id and 
                    message.channel.id == interaction.channel.id and 
                    message.attachments)
        
        try:
            # Wait for a message with an attachment
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            
            if not msg.attachments or not msg.attachments[0].content_type.startswith('image/gif'):
                await interaction.followup.send("Прикрепленный файл не является GIF-анимацией.", ephemeral=True)
                return
            
            # Download the GIF
            attachment = msg.attachments[0]
            gif_data = await attachment.read()
            
            # Save GIF to file
            gif_path = save_gif_file(gif_id, gif_data)
            if not gif_path:
                await interaction.followup.send("Произошла ошибка при сохранении GIF-файла.", ephemeral=True)
                return
            
            # Store GIF metadata
            self.gifs[gif_id] = {
                "name": gif_name,
                "path": gif_path,
                "uploaded_by": str(interaction.user.id),
                "uploaded_at": datetime.now().timestamp()
            }
            save_gifs(self.gifs)
            
            # Delete the message with the attachment
            try:
                await msg.delete()
            except:
                pass
            
            await interaction.followup.send(f"GIF-анимация **{gif_name}** успешно загружена и сохранена с ID **{gif_id}**.", ephemeral=True)
            logger.info(f"User {interaction.user.id} uploaded GIF animation with ID {gif_id}")
        except asyncio.TimeoutError:
            await interaction.followup.send("Время ожидания истекло. Пожалуйста, попробуйте снова.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error uploading GIF: {e}")
            await interaction.followup.send(f"Произошла ошибка при загрузке GIF-анимации: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="listgifs", description="Показать список доступных GIF-анимаций")
    @app_commands.default_permissions(administrator=True)
    async def list_gifs(self, interaction: discord.Interaction):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        if not self.gifs:
            await interaction.response.send_message("Список GIF-анимаций пуст.", ephemeral=True)
            return
        
        # Create embed
        embed = discord.Embed(
            title="Список доступных GIF-анимаций",
            color=discord.Color.blue()
        )
        
        for gif_id, gif_data in self.gifs.items():
            if isinstance(gif_data, dict):
                name = gif_data.get("name", "Без названия")
                upload_time = datetime.fromtimestamp(gif_data.get("uploaded_at", 0)).strftime("%d.%m.%Y %H:%M")
                embed.add_field(
                    name=f"ID: {gif_id}",
                    value=f"**Название:** {name}\n**Загружено:** {upload_time}",
                    inline=True
                )
            else:
                # Handle old format if needed
                embed.add_field(
                    name=f"ID: {gif_id}",
                    value=f"**Название:** {gif_data}",
                    inline=True
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="attachgif", description="Прикрепить GIF-анимацию к розыгрышу")
    @app_commands.describe(
        giveaway_id="ID розыгрыша",
        gif_id="ID GIF-анимации для прикрепления"
    )
    @app_commands.default_permissions(administrator=True)
    async def attach_gif(self, interaction: discord.Interaction, giveaway_id: str, gif_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Validate giveaway ID
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Розыгрыш с указанным ID не найден.", ephemeral=True)
            return
        
        # Validate GIF ID
        if gif_id not in self.gifs:
            await interaction.response.send_message("GIF-анимация с указанным ID не найдена.", ephemeral=True)
            return
        
        giveaway = self.giveaways[giveaway_id]
        
        if giveaway.get("ended", False):
            await interaction.response.send_message("Невозможно прикрепить GIF-анимацию к завершенному розыгрышу.", ephemeral=True)
            return
        
        # Attach GIF to giveaway
        giveaway["celebration_gif"] = gif_id
        save_giveaways(self.giveaways)
        
        # Get GIF name for the message
        gif_name = self.gifs[gif_id]["name"] if isinstance(self.gifs[gif_id], dict) else self.gifs[gif_id]
        
        await interaction.response.send_message(
            f"GIF-анимация **{gif_name}** успешно прикреплена к розыгрышу **{giveaway['title']}**.",
            ephemeral=True
        )
        logger.info(f"GIF {gif_id} attached to giveaway {giveaway_id}")
        
    @app_commands.command(name="assignprizes", description="Назначить список призов для конкретного розыгрыша")
    @app_commands.describe(
        giveaway_id="ID розыгрыша", 
        prize_ids="Список ID призов через запятую или диапазон (например, '1,2,3' или '1-3')"
    )
    @app_commands.default_permissions(administrator=True)
    async def assign_prizes(self, interaction: discord.Interaction, giveaway_id: str, prize_ids: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Validate giveaway ID
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Розыгрыш с указанным ID не найден.", ephemeral=True)
            return
        
        giveaway = self.giveaways[giveaway_id]
        
        if giveaway.get("ended", False):
            await interaction.response.send_message("Невозможно назначить призы для завершенного розыгрыша.", ephemeral=True)
            return
        
        # Process prize IDs with enhanced parsing including ranges
        assigned_prizes, missing_prizes = parse_prize_ids(prize_ids, self.prizes)
        
        if not assigned_prizes:
            await interaction.response.send_message("Ни один из указанных ID призов не найден.", ephemeral=True)
            return
        
        # Assign prizes to the giveaway
        giveaway["assigned_prizes"] = assigned_prizes
        save_giveaways(self.giveaways)
        
        # Prepare response message
        message = f"Для розыгрыша **{giveaway['title']}** назначены следующие призы:\n"
        for pid, prize_name in assigned_prizes.items():
            message += f"- **{prize_name}** (ID: {pid})\n"
        
        if missing_prizes:
            message += f"\nСледующие ID призов не найдены: {', '.join(missing_prizes)}"
        
        await interaction.response.send_message(message, ephemeral=True)
        logger.info(f"Assigned prizes {list(assigned_prizes.keys())} to giveaway {giveaway_id}")
    
    @app_commands.command(name="createprizelist", description="Создать список призов из текстового файла")
    @app_commands.describe(
        list_id="Уникальный идентификатор списка призов",
        list_name="Название списка призов для отображения"
    )
    @app_commands.default_permissions(administrator=True)
    async def create_prize_list(self, interaction: discord.Interaction, list_id: str, list_name: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Check if list ID already exists
        if list_id in self.prize_lists:
            await interaction.response.send_message("Список призов с таким ID уже существует. Используйте другой ID.", ephemeral=True)
            return
        
        # Send initial response
        await interaction.response.send_message(
            "Пожалуйста, отправьте текстовый файл (.txt) со списком призов в следующем сообщении.\n\n"
            "Каждая строка файла должна содержать один приз в формате: `ID:Название`\n"
            "Например:\n"
            "```\n"
            "1:Приз №1\n"
            "2:Приз №2\n"
            "3:Приз №3\n"
            "```",
            ephemeral=True
        )
        
        # Define a check for the attachment in the follow-up message
        def check(message):
            return (message.author.id == interaction.user.id and 
                    message.channel.id == interaction.channel.id and 
                    message.attachments and
                    message.attachments[0].filename.endswith('.txt'))
        
        try:
            # Wait for a message with an attachment
            msg = await self.bot.wait_for('message', check=check, timeout=60.0)
            
            # Download the text file
            attachment = msg.attachments[0]
            content = await attachment.read()
            content_text = content.decode('utf-8')
            
            # Parse the prize list
            prizes = {}
            valid_lines = []
            invalid_lines = []
            
            # Process each line
            for i, line in enumerate(content_text.strip().split('\n')):
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                # Check if line has the format "ID:Name"
                if ':' in line:
                    parts = line.split(':', 1)
                    if len(parts) == 2:
                        prize_id, prize_name = parts[0].strip(), parts[1].strip()
                        if prize_id and prize_name:
                            prizes[prize_id] = prize_name
                            valid_lines.append(f"{prize_id}: {prize_name}")
                            continue
                
                # If we reached here, the line is invalid
                invalid_lines.append(f"Строка {i+1}: {line}")
            
            # Save the prize list file
            if not prizes:
                await interaction.followup.send("В файле не найдены корректные записи призов. Формат должен быть 'ID:Название'.", ephemeral=True)
                return
            
            # Save the file content
            file_path = save_prize_list_file(list_id, content_text)
            if not file_path:
                await interaction.followup.send("Произошла ошибка при сохранении файла со списком призов.", ephemeral=True)
                return
            
            # Save prize list metadata
            self.prize_lists[list_id] = {
                "name": list_name,
                "path": file_path,
                "created_by": str(interaction.user.id),
                "created_at": datetime.now().timestamp(),
                "prize_count": len(prizes)
            }
            save_prize_lists(self.prize_lists)
            
            # Delete the message with the attachment
            try:
                await msg.delete()
            except:
                pass
            
            # Send response
            embed = discord.Embed(
                title=f"✅ Список призов создан: {list_name}",
                description=f"ID списка: `{list_id}`\nКоличество призов: {len(prizes)}",
                color=discord.Color.green()
            )
            
            # Show some prizes as a preview (limit to 10)
            preview_lines = valid_lines[:10]
            if preview_lines:
                embed.add_field(
                    name="Предпросмотр призов",
                    value="```\n" + "\n".join(preview_lines) + "\n```" + 
                          (f"\n... и еще {len(valid_lines) - 10} призов" if len(valid_lines) > 10 else ""),
                    inline=False
                )
            
            # Show invalid lines if any
            if invalid_lines:
                embed.add_field(
                    name="⚠️ Некорректные строки (пропущены)",
                    value="```\n" + "\n".join(invalid_lines[:5]) + "\n```" + 
                          (f"\n... и еще {len(invalid_lines) - 5} некорректных строк" if len(invalid_lines) > 5 else ""),
                    inline=False
                )
            
            await interaction.followup.send(embed=embed, ephemeral=True)
            logger.info(f"User {interaction.user.id} created prize list with ID {list_id} containing {len(prizes)} prizes")
            
        except asyncio.TimeoutError:
            await interaction.followup.send("Время ожидания истекло. Пожалуйста, попробуйте снова.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating prize list: {e}")
            await interaction.followup.send(f"Произошла ошибка при создании списка призов: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="listprizelists", description="Показать все доступные списки призов")
    @app_commands.default_permissions(administrator=True)
    async def list_prize_lists(self, interaction: discord.Interaction):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        if not self.prize_lists:
            await interaction.response.send_message("Нет доступных списков призов.", ephemeral=True)
            return
        
        # Create embed
        embed = discord.Embed(
            title="📋 Доступные списки призов",
            color=discord.Color.blue()
        )
        
        for list_id, list_data in self.prize_lists.items():
            if isinstance(list_data, dict):
                name = list_data.get("name", "Без названия")
                prize_count = list_data.get("prize_count", "Неизвестно")
                created_at = datetime.fromtimestamp(list_data.get("created_at", 0)).strftime("%d.%m.%Y %H:%M")
                
                embed.add_field(
                    name=f"ID: {list_id}",
                    value=f"**Название:** {name}\n**Количество призов:** {prize_count}\n**Создан:** {created_at}",
                    inline=True
                )
            else:
                # Handle old format if needed
                embed.add_field(
                    name=f"ID: {list_id}",
                    value=f"**Название:** {list_data}",
                    inline=True
                )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
    @app_commands.command(name="viewprizelist", description="Просмотреть содержимое списка призов")
    @app_commands.describe(list_id="ID списка призов")
    @app_commands.default_permissions(administrator=True)
    async def view_prize_list(self, interaction: discord.Interaction, list_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Validate list ID
        if list_id not in self.prize_lists:
            await interaction.response.send_message("Список призов с указанным ID не найден.", ephemeral=True)
            return
        
        # Load the prize list content
        content = load_prize_list_file(list_id)
        if content is None:
            await interaction.response.send_message("Не удалось загрузить содержимое списка призов.", ephemeral=True)
            return
        
        # Parse prizes
        prizes = {}
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):  # Skip empty lines and comments
                continue
            
            # Check if line has the format "ID:Name"
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    prize_id, prize_name = parts[0].strip(), parts[1].strip()
                    if prize_id and prize_name:
                        prizes[prize_id] = prize_name
        
        # Prepare embed
        list_data = self.prize_lists[list_id]
        embed = discord.Embed(
            title=f"📋 Список призов: {list_data.get('name', list_id)}",
            description=f"ID списка: `{list_id}`\nВсего призов: {len(prizes)}",
            color=discord.Color.blue()
        )
        
        # Show prizes in chunks due to Discord's field limit
        # We'll create multiple fields, each with up to 15 prizes
        prize_items = list(prizes.items())
        
        for i in range(0, len(prize_items), 15):
            chunk = prize_items[i:i+15]
            embed.add_field(
                name=f"Призы {i+1}-{i+len(chunk)}",
                value="\n".join([f"`{pid}`: {name}" for pid, name in chunk]),
                inline=False
            )
        
        # If there are too many prizes, create a file attachment
        if len(prizes) > 50:
            file = discord.File(
                fp=f"{PRIZE_LISTS_DIR}/{list_id}.txt",
                filename=f"prizes_{list_id}.txt"
            )
            await interaction.response.send_message(
                content="Список призов слишком большой, поэтому прикреплен как файл:",
                embed=embed,
                file=file,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            
    @app_commands.command(name="removeprizelist", description="Удалить список призов")
    @app_commands.describe(list_id="ID списка призов для удаления")
    @app_commands.default_permissions(administrator=True)
    async def remove_prize_list(self, interaction: discord.Interaction, list_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Validate list ID
        if list_id not in self.prize_lists:
            await interaction.response.send_message("Список призов с указанным ID не найден.", ephemeral=True)
            return
        
        # Get list name for the message
        list_name = self.prize_lists[list_id].get("name", list_id) if isinstance(self.prize_lists[list_id], dict) else self.prize_lists[list_id]
        
        # Remove the list from memory and save
        del self.prize_lists[list_id]
        save_prize_lists(self.prize_lists)
        
        # Try to delete the file
        try:
            file_path = f"{PRIZE_LISTS_DIR}/{list_id}.txt"
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.error(f"Error deleting prize list file: {e}")
        
        await interaction.response.send_message(f"Список призов **{list_name}** успешно удален.", ephemeral=True)
        logger.info(f"User {interaction.user.id} removed prize list with ID {list_id}")
        
    @app_commands.command(name="assignprizelist", description="Назначить список призов для розыгрыша")
    @app_commands.describe(
        giveaway_id="ID розыгрыша",
        list_id="ID списка призов"
    )
    @app_commands.default_permissions(administrator=True)
    async def assign_prize_list(self, interaction: discord.Interaction, giveaway_id: str, list_id: str):
        # Проверяем разрешения и права администратора
        if not await self.is_admin(interaction):
            return
        
        # Validate giveaway ID
        if giveaway_id not in self.giveaways:
            await interaction.response.send_message("Розыгрыш с указанным ID не найден.", ephemeral=True)
            return
        
        # Validate list ID
        if list_id not in self.prize_lists:
            await interaction.response.send_message("Список призов с указанным ID не найден.", ephemeral=True)
            return
        
        giveaway = self.giveaways[giveaway_id]
        
        if giveaway.get("ended", False):
            await interaction.response.send_message("Невозможно назначить список призов для завершенного розыгрыша.", ephemeral=True)
            return
        
        # Load the prize list
        content = load_prize_list_file(list_id)
        if content is None:
            await interaction.response.send_message("Не удалось загрузить содержимое списка призов.", ephemeral=True)
            return
        
        # Parse prizes
        prizes = {}
        for line in content.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('#'):  # Skip empty lines and comments
                continue
            
            # Check if line has the format "ID:Name"
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    prize_id, prize_name = parts[0].strip(), parts[1].strip()
                    if prize_id and prize_name:
                        prizes[prize_id] = prize_name
        
        if not prizes:
            await interaction.response.send_message("В выбранном списке призов не найдено ни одного корректного приза.", ephemeral=True)
            return
        
        # Assign prizes to the giveaway
        giveaway["assigned_prizes"] = prizes
        giveaway["prize_list_id"] = list_id
        save_giveaways(self.giveaways)
        
        # Get list name
        list_name = self.prize_lists[list_id].get("name", list_id) if isinstance(self.prize_lists[list_id], dict) else self.prize_lists[list_id]
        
        # Send confirmation message
        await interaction.response.send_message(
            f"Для розыгрыша **{giveaway['title']}** назначен список призов **{list_name}** "
            f"с {len(prizes)} призами.",
            ephemeral=True
        )
        logger.info(f"Assigned prize list {list_id} to giveaway {giveaway_id}")

async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
