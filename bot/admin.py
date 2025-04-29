import logging
from typing import Dict, List, Optional, Tuple
import re

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext

from bot.database import Database
from bot import config

logger = logging.getLogger(__name__)
db = Database()

# Admin command handlers
async def admin_command(update: Update, context: CallbackContext) -> None:
    """Handle the /admin command - show admin panel"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return
    
    keyboard = [
        [InlineKeyboardButton("👥 Adminlarni boshqarish", callback_data="admin_manage_admins")],
        [InlineKeyboardButton("👑 Premium foydalanuvchilarni boshqarish", callback_data="admin_manage_premium")],
        [InlineKeyboardButton("📢 Majburiy kanallarni boshqarish", callback_data="admin_manage_channels")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📨 Xabar yuborish", callback_data="admin_broadcast")]
    ]
    
    await update.message.reply_text(
        "🔐 *Admin panel*\n\nQuyidagi amallardan birini tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_callback_handler(update: Update, context: CallbackContext) -> None:
    """Handle admin panel callbacks"""
    query = update.callback_query
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        try:
            await query.answer("Bu amal faqat adminlar uchun.", show_alert=True)
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
        return
    
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback query: {e}")
        # Continue anyway, as this is not critical
    
    callback_data = query.data
    
    try:
        if callback_data == "admin_manage_admins":
            await show_manage_admins(query, context)
        elif callback_data == "admin_manage_premium":
            await show_manage_premium(query, context)
        elif callback_data == "admin_manage_channels":
            await show_manage_channels(query, context)
        elif callback_data == "admin_stats":
            await show_stats(query, context)
        elif callback_data == "admin_broadcast":
            await show_broadcast(query, context)
        elif callback_data.startswith("admin_add_admin_"):
            await add_admin_command(update, context)
        elif callback_data.startswith("admin_remove_admin_"):
            user_id_to_remove = int(callback_data.split("_")[-1])
            await remove_admin(query, context, user_id_to_remove)
        elif callback_data == "admin_add_premium":
            await add_premium_command(update, context)
        elif callback_data.startswith("admin_remove_premium_"):
            user_id_to_remove = int(callback_data.split("_")[-1])
            await remove_premium(query, context, user_id_to_remove)
        elif callback_data == "admin_add_channel":
            await add_channel_command(update, context)
        elif callback_data.startswith("admin_remove_channel_"):
            channel_id = callback_data.split("_")[-1]
            await remove_channel(query, context, channel_id)
        elif callback_data == "admin_back":
            await show_admin_panel(query, context)
        elif callback_data == "admin_confirm_broadcast":
            await confirm_broadcast(update, context)
    except Exception as e:
        logger.error(f"Error handling admin callback: {e}")
        try:
            await query.edit_message_text(
                f"⚠️ Xatolik yuz berdi: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
            )
        except Exception:
            pass

async def show_admin_panel(query, context: CallbackContext) -> None:
    """Show the main admin panel"""
    keyboard = [
        [InlineKeyboardButton("👥 Adminlarni boshqarish", callback_data="admin_manage_admins")],
        [InlineKeyboardButton("👑 Premium foydalanuvchilarni boshqarish", callback_data="admin_manage_premium")],
        [InlineKeyboardButton("📢 Majburiy kanallarni boshqarish", callback_data="admin_manage_channels")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("📨 Xabar yuborish", callback_data="admin_broadcast")]
    ]
    
    try:
        await query.edit_message_text(
            "🔐 *Admin panel*\n\nQuyidagi amallardan birini tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing admin panel: {e}")

async def show_manage_admins(query, context: CallbackContext) -> None:
    """Show admin management panel"""
    try:
        admins = db.get_all_admins()
        
        keyboard = []
        for admin in admins:
            name = admin['username'] or f"{admin['first_name']} {admin['last_name']}"
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {name}", 
                    callback_data=f"admin_remove_admin_{admin['user_id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Admin qo'shish", callback_data="admin_add_admin_")])
        keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")])
        
        await query.edit_message_text(
            "👥 *Adminlarni boshqarish*\n\n"
            "Admin o'chirish uchun adminni tanlang yoki yangi admin qo'shing:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing manage admins: {e}")
        await query.edit_message_text(
            "⚠️ Adminlarni ko'rsatishda xatolik yuz berdi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
        )

async def show_manage_premium(query, context: CallbackContext) -> None:
    """Show premium users management panel"""
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT user_id, username, first_name, last_name 
                FROM users 
                WHERE is_premium = 1
            """)
            
            premium_users = []
            for row in cursor.fetchall():
                premium_users.append(dict(row))
            
            keyboard = []
            for user in premium_users:
                name = user['username'] or f"{user['first_name']} {user['last_name']}" or f"ID: {user['user_id']}"
                keyboard.append([
                    InlineKeyboardButton(
                        f"❌ {name}", 
                        callback_data=f"admin_remove_premium_{user['user_id']}"
                    )
                ])
            
            keyboard.append([InlineKeyboardButton("➕ Premium foydalanuvchi qo'shish", callback_data="admin_add_premium")])
            keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")])
            
            await query.edit_message_text(
                "👑 *Premium foydalanuvchilarni boshqarish*\n\n"
                "Premium statusni o'chirish uchun foydalanuvchini tanlang yoki yangi premium foydalanuvchi qo'shing:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Error showing manage premium users: {e}")
        await query.edit_message_text(
            "⚠️ Premium foydalanuvchilarni ko'rsatishda xatolik yuz berdi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
        )

async def show_manage_channels(query, context: CallbackContext) -> None:
    """Show channel management panel"""
    try:
        channels = db.get_all_required_channels()
        
        keyboard = []
        for channel in channels:
            keyboard.append([
                InlineKeyboardButton(
                    f"❌ {channel['channel_name']}", 
                    callback_data=f"admin_remove_channel_{channel['channel_id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("➕ Kanal qo'shish", callback_data="admin_add_channel")])
        keyboard.append([InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")])
        
        await query.edit_message_text(
            "📢 *Majburiy kanallarni boshqarish*\n\n"
            "Kanal o'chirish uchun kanalni tanlang yoki yangi kanal qo'shing:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing manage channels: {e}")
        await query.edit_message_text(
            "⚠️ Kanallarni ko'rsatishda xatolik yuz berdi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
        )

async def show_stats(query, context: CallbackContext) -> None:
    """Show bot statistics"""
    try:
        conn = db._get_connection()
        cursor = conn.cursor()
        
        try:
            # Get total users
            cursor.execute("SELECT COUNT(*) as count FROM users")
            total_users = cursor.fetchone()['count']
            
            # Get active users (last 7 days)
            cursor.execute("""
                SELECT COUNT(*) as count FROM users 
                WHERE datetime(last_interaction) > datetime('now', '-7 days')
            """)
            active_users = cursor.fetchone()['count']
            
            # Get premium users
            cursor.execute("SELECT COUNT(*) as count FROM users WHERE is_premium = 1")
            premium_users = cursor.fetchone()['count']
            
            # Get total presentations created
            cursor.execute("SELECT SUM(presentations_created) as total FROM users")
            result = cursor.fetchone()
            total_presentations = result['total'] if result and result['total'] is not None else 0
            
            # Get total abstracts created
            cursor.execute("SELECT SUM(abstracts_created) as total FROM users")
            result = cursor.fetchone()
            total_abstracts = result['total'] if result and result['total'] is not None else 0
            
            stats_text = (
                "📊 *Bot statistikasi*\n\n"
                f"👤 Jami foydalanuvchilar: {total_users}\n"
                f"🟢 Faol foydalanuvchilar (7 kun): {active_users}\n"
                f"👑 Premium foydalanuvchilar: {premium_users}\n"
                f"📊 Jami yaratilgan taqdimotlar: {total_presentations:,}\n"
                f"📝 Jami yaratilgan abstraktlar: {total_abstracts:,}"
            )
            
            keyboard = [[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]]
            
            await query.edit_message_text(
                stats_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Error showing stats: {e}")
        await query.edit_message_text(
            "⚠️ Statistikani ko'rsatishda xatolik yuz berdi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
        )

async def show_broadcast(query, context: CallbackContext) -> None:
    """Show broadcast message panel"""
    context.user_data['admin_state'] = 'waiting_for_broadcast'
    
    try:
        await query.edit_message_text(
            "📨 *Xabar yuborish*\n\n"
            "Barcha foydalanuvchilarga yubormoqchi bo'lgan xabarni kiriting:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="admin_back")]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing broadcast: {e}")

async def add_admin_command(update: Update, context: CallbackContext) -> None:
    """Start the process of adding a new admin"""
    query = update.callback_query
    context.user_data['admin_state'] = 'waiting_for_admin_id'
    
    try:
        await query.edit_message_text(
            "👤 *Admin qo'shish*\n\n"
            "Yangi admin qo'shish uchun uning Telegram ID raqamini kiriting:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="admin_manage_admins")]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing add admin: {e}")

async def add_premium_command(update: Update, context: CallbackContext) -> None:
    """Start the process of adding a new premium user"""
    query = update.callback_query
    context.user_data['admin_state'] = 'waiting_for_premium_id'
    
    try:
        await query.edit_message_text(
            "👑 *Premium foydalanuvchi qo'shish*\n\n"
            "Yangi premium foydalanuvchi qo'shish uchun uning Telegram ID raqamini kiriting:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="admin_manage_premium")]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing add premium: {e}")

async def add_admin(update: Update, context: CallbackContext) -> None:
    """Add a new admin based on user input"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("Bu amal faqat adminlar uchun.")
        return
    
    if 'admin_state' not in context.user_data or context.user_data['admin_state'] != 'waiting_for_admin_id':
        return
    
    try:
        new_admin_id = int(update.message.text.strip())
        
        # Check if user exists in database
        if not db.check_if_user_exists(new_admin_id):
            await update.message.reply_text(
                "⚠️ Bu foydalanuvchi botdan hali foydalanmagan. "
                "Foydalanuvchi avval bot bilan muloqot qilishi kerak."
            )
            return
        
        # Check if already admin
        if db.is_admin(new_admin_id):
            await update.message.reply_text("⚠️ Bu foydalanuvchi allaqachon admin.")
            return
        
        # Set as admin
        db.set_admin_status(new_admin_id, True)
        
        # Get username or name
        try:
            username = db.get_user_attribute(new_admin_id, "username")
            first_name = db.get_user_attribute(new_admin_id, "first_name")
            name = username or first_name or f"ID: {new_admin_id}"
        except:
            name = f"ID: {new_admin_id}"
        
        await update.message.reply_text(f"✅ {name} muvaffaqiyatli admin qilindi!")
        
        # Reset state
        context.user_data.pop('admin_state', None)
        
        # Show admin panel again
        keyboard = [
            [InlineKeyboardButton("👥 Adminlarni boshqarish", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("👑 Premium foydalanuvchilarni boshqarish", callback_data="admin_manage_premium")],
            [InlineKeyboardButton("📢 Majburiy kanallarni boshqarish", callback_data="admin_manage_channels")],
            [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton("📨 Xabar yuborish", callback_data="admin_broadcast")]
        ]
        
        await update.message.reply_text(
            "🔐 *Admin panel*\n\nQuyidagi amallardan birini tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text("⚠️ Noto'g'ri format. Iltimos, raqam kiriting.")

async def add_premium(update: Update, context: CallbackContext) -> None:
    """Add a new premium user based on user input"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("Bu amal faqat adminlar uchun.")
        return
    
    if 'admin_state' not in context.user_data or context.user_data['admin_state'] != 'waiting_for_premium_id':
        return
    
    try:
        new_premium_id = int(update.message.text.strip())
        
        # Check if user exists in database
        if not db.check_if_user_exists(new_premium_id):
            await update.message.reply_text(
                "⚠️ Bu foydalanuvchi botdan hali foydalanmagan. "
                "Foydalanuvchi avval bot bilan muloqot qilishi kerak."
            )
            return
        
        # Check if already premium
        if db.is_premium(new_premium_id):
            await update.message.reply_text("⚠️ Bu foydalanuvchi allaqachon premium obunachi.")
            return
        
        # Set as premium
        db.set_premium_status(new_premium_id, True)
        
        # Get username or name
        try:
            username = db.get_user_attribute(new_premium_id, "username")
            first_name = db.get_user_attribute(new_premium_id, "first_name")
            name = username or first_name or f"ID: {new_premium_id}"
        except:
            name = f"ID: {new_premium_id}"
        
        await update.message.reply_text(f"✅ {name} muvaffaqiyatli premium obunachi qilindi!")
        
        # Reset state
        context.user_data.pop('admin_state', None)
        
        # Show admin panel again
        keyboard = [
            [InlineKeyboardButton("👥 Adminlarni boshqarish", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("👑 Premium foydalanuvchilarni boshqarish", callback_data="admin_manage_premium")],
            [InlineKeyboardButton("📢 Majburiy kanallarni boshqarish", callback_data="admin_manage_channels")],
            [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton("📨 Xabar yuborish", callback_data="admin_broadcast")]
        ]
        
        await update.message.reply_text(
            "🔐 *Admin panel*\n\nQuyidagi amallardan birini tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text("⚠️ Noto'g'ri format. Iltimos, raqam kiriting.")

async def remove_admin(query, context: CallbackContext, user_id_to_remove: int) -> None:
    """Remove an admin"""
    admin_id = query.from_user.id
    
    try:
        # Don't allow admins to remove themselves
        if admin_id == user_id_to_remove:
            await query.edit_message_text(
                "⚠️ Siz o'zingizni admin ro'yxatidan o'chira olmaysiz.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_admins")]])
            )
            return
        
        # Remove admin status
        db.set_admin_status(user_id_to_remove, False)
        
        # Get username or name
        try:
            username = db.get_user_attribute(user_id_to_remove, "username")
            first_name = db.get_user_attribute(user_id_to_remove, "first_name")
            name = username or first_name or f"ID: {user_id_to_remove}"
        except:
            name = f"ID: {user_id_to_remove}"
        
        await query.edit_message_text(
            f"✅ {name} admin ro'yxatidan o'chirildi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_admins")]])
        )
    except Exception as e:
        logger.error(f"Error removing admin: {e}")
        await query.edit_message_text(
            "⚠️ Adminni o'chirishda xatolik yuz berdi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_admins")]])
        )

async def remove_premium(query, context: CallbackContext, user_id_to_remove: int) -> None:
    """Remove premium status from a user"""
    try:
        # Remove premium status
        db.set_premium_status(user_id_to_remove, False)
        
        # Get username or name
        try:
            username = db.get_user_attribute(user_id_to_remove, "username")
            first_name = db.get_user_attribute(user_id_to_remove, "first_name")
            name = username or first_name or f"ID: {user_id_to_remove}"
        except:
            name = f"ID: {user_id_to_remove}"
        
        await query.edit_message_text(
            f"✅ {name} premium obuna ro'yxatidan o'chirildi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_premium")]])
        )
    except Exception as e:
        logger.error(f"Error removing premium: {e}")
        await query.edit_message_text(
            "⚠️ Premium statusni o'chirishda xatolik yuz berdi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_premium")]])
        )

async def add_channel_command(update: Update, context: CallbackContext) -> None:
    """Start the process of adding a new required channel"""
    query = update.callback_query
    context.user_data['admin_state'] = 'waiting_for_channel_info'
    
    try:
        await query.edit_message_text(
            "📢 *Majburiy kanal qo'shish*\n\n"
            "Quyidagi formatda kanal ma'lumotlarini kiriting:\n"
            "`@username yoki -100... | Kanal nomi | https://t.me/...`\n\n"
            "Misol:\n"
            "`@mychannel | Mening kanalam | https://t.me/mychannel`\n"
            "yoki\n"
            "`-1001234567890 | Mening kanalam | https://t.me/joinchat/...`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Bekor qilish", callback_data="admin_manage_channels")]]),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing add channel: {e}")

async def add_channel(update: Update, context: CallbackContext) -> None:
    """Add a new required channel based on user input"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("Bu amal faqat adminlar uchun.")
        return
    
    if 'admin_state' not in context.user_data or context.user_data['admin_state'] != 'waiting_for_channel_info':
        return
    
    try:
        # Parse channel info
        text = update.message.text.strip()
        
        # Check if this is just a channel ID or username
        if "|" not in text:
            # Try to extract channel info automatically
            channel_id = text.strip()
            
            # Clean up the channel ID
            if channel_id.startswith('@'):
                # It's a username
                pass
            elif channel_id.startswith('-100'):
                # It's a channel ID
                pass
            else:
                # Try to convert to proper format
                try:
                    # If it's a numeric ID without -100 prefix
                    if channel_id.isdigit():
                        channel_id = f"-100{channel_id}"
                    # If it's a URL
                    elif "t.me/" in channel_id:
                        if "t.me/joinchat/" in channel_id or "t.me/+" in channel_id:
                            # Private channel link, need to ask for ID
                            await update.message.reply_text(
                                "⚠️ Bu havola uchun kanal ID raqamini ham kiriting. Masalan:\n"
                                "-1001234567890 | Kanal nomi | https://t.me/joinchat/..."
                            )
                            return
                        else:
                            # Public channel link
                            username = channel_id.split("t.me/")[1].split("/")[0]
                            channel_id = f"@{username}"
                    else:
                        await update.message.reply_text(
                            "⚠️ Noto'g'ri format. Iltimos, quyidagi formatda kiriting:\n"
                            "`@username yoki -100... | Kanal nomi | https://t.me/...`"
                        )
                        return
                except Exception:
                    await update.message.reply_text(
                        "⚠️ Noto'g'ri format. Iltimos, quyidagi formatda kiriting:\n"
                        "`@username yoki -100... | Kanal nomi | https://t.me/...`"
                    )
                    return
            
            # Try to get channel info
            try:
                chat = await context.bot.get_chat(channel_id)
                channel_name = chat.title
                if chat.username:
                    channel_link = f"https://t.me/{chat.username}"
                else:
                    # For private channels, use invite link if available
                    try:
                        invite_link = await context.bot.export_chat_invite_link(chat.id)
                        channel_link = invite_link
                    except Exception:
                        channel_link = "https://t.me/"  # Fallback
            except Exception as e:
                await update.message.reply_text(
                    f"⚠️ Kanal ma'lumotlarini olishda xatolik: {str(e)}\n"
                    "Iltimos, to'liq formatda kiriting:\n"
                    "`@username yoki -100... | Kanal nomi | https://t.me/...`"
                )
                return
        else:
            # Standard format with pipe separators
            channel_info = text.split('|')
            if len(channel_info) != 3:
                await update.message.reply_text(
                    "⚠️ Noto'g'ri format. Iltimos, quyidagi formatda kiriting:\n"
                    "`@username yoki -100... | Kanal nomi | https://t.me/...`"
                )
                return
            
            channel_id = channel_info[0].strip()
            channel_name = channel_info[1].strip()
            channel_link = channel_info[2].strip()
        
        # Validate channel ID
        if not (channel_id.startswith('@') or channel_id.startswith('-100')):
            await update.message.reply_text(
                "⚠️ Noto'g'ri kanal ID. Kanal ID @username yoki -100... formatida bo'lishi kerak."
            )
            return
        
        # Validate channel link if provided in standard format
        if "|" in text and not (channel_link.startswith('https://t.me/') or channel_link.startswith('https://t.me/joinchat/') or channel_link.startswith('https://t.me/+')):
            await update.message.reply_text(
                "⚠️ Noto'g'ri kanal havolasi. Havola https://t.me/ bilan boshlanishi kerak."
            )
            return
        
        # Check if bot is a member of the channel
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel_id, user_id=context.bot.id)
            if chat_member.status not in ['administrator', 'member']:
                await update.message.reply_text(
                    "⚠️ Bot bu kanalga a'zo emas yoki admin emas. "
                    "Iltimos, avval botni kanalga admin sifatida qo'shing."
                )
                return
        except Exception as e:
            await update.message.reply_text(
                f"⚠️ Kanal tekshirishda xatolik: {str(e)}\n"
                "Iltimos, kanal ID to'g'ri ekanligini tekshiring va botni kanalga admin sifatida qo'shing."
            )
            return
        
        # Add channel to database
        channel_id_db = db.add_required_channel(channel_id, channel_name, channel_link, user_id)
        
        if channel_id_db > 0:
            await update.message.reply_text(f"✅ {channel_name} majburiy kanallar ro'yxatiga qo'shildi!")
        else:
            await update.message.reply_text("⚠️ Kanal qo'shishda xatolik yuz berdi.")
        
        # Reset state
        context.user_data.pop('admin_state', None)
        
        # Show admin panel again
        keyboard = [
            [InlineKeyboardButton("👥 Adminlarni boshqarish", callback_data="admin_manage_admins")],
            [InlineKeyboardButton("👑 Premium foydalanuvchilarni boshqarish", callback_data="admin_manage_premium")],
            [InlineKeyboardButton("📢 Majburiy kanallarni boshqarish", callback_data="admin_manage_channels")],
            [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
            [InlineKeyboardButton("📨 Xabar yuborish", callback_data="admin_broadcast")]
        ]
        
        await update.message.reply_text(
            "🔐 *Admin panel*\n\nQuyidagi amallardan birini tanlang:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error adding channel: {e}")
        await update.message.reply_text(f"⚠️ Xatolik yuz berdi: {str(e)}")

async def remove_channel(query, context: CallbackContext, channel_id: str) -> None:
    """Remove a required channel"""
    try:
        # Get channel info before removing
        channel = db.get_required_channel(channel_id)
        
        if not channel:
            await query.edit_message_text(
                "⚠️ Kanal topilmadi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_channels")]])
            )
            return
        
        # Remove channel
        success = db.remove_required_channel(channel_id)
        
        if success:
            await query.edit_message_text(
                f"✅ {channel['channel_name']} majburiy kanallar ro'yxatidan o'chirildi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_channels")]])
            )
        else:
            await query.edit_message_text(
                "⚠️ Kanalni o'chirishda xatolik yuz berdi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_channels")]])
            )
    except Exception as e:
        logger.error(f"Error removing channel: {e}")
        await query.edit_message_text(
            "⚠️ Kanalni o'chirishda xatolik yuz berdi.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_manage_channels")]])
        )

async def broadcast_message(update: Update, context: CallbackContext) -> None:
    """Broadcast a message to all users"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        await update.message.reply_text("Bu amal faqat adminlar uchun.")
        return
    
    if 'admin_state' not in context.user_data or context.user_data['admin_state'] != 'waiting_for_broadcast':
        return
    
    broadcast_text = update.message.text
    
    # Confirm broadcast
    await update.message.reply_text(
        "📨 *Xabarni yuborish*\n\n"
        f"Quyidagi xabar barcha foydalanuvchilarga yuboriladi:\n\n"
        f"{broadcast_text}\n\n"
        "Davom etasizmi?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ha", callback_data="admin_confirm_broadcast")],
            [InlineKeyboardButton("❌ Yo'q", callback_data="admin_back")]
        ]),
        parse_mode='Markdown'
    )
    
    # Save broadcast text
    context.user_data['broadcast_text'] = broadcast_text

async def confirm_broadcast(update: Update, context: CallbackContext) -> None:
    """Confirm and send broadcast message to all users"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not db.is_admin(user_id):
        try:
            await query.answer("Bu amal faqat adminlar uchun.", show_alert=True)
        except Exception as e:
            logger.error(f"Error answering callback query: {e}")
        return
    
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback query: {e}")
        # Continue anyway, as this is not critical
    
    if 'broadcast_text' not in context.user_data:
        try:
            await query.edit_message_text(
                "⚠️ Xabar topilmadi.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
        return
    
    broadcast_text = context.user_data['broadcast_text']
    
    try:
        # Get all users
        conn = db._get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT user_id, chat_id FROM users")
            users = cursor.fetchall()
            
            # Send status message
            status_message = await query.edit_message_text(
                f"📨 Xabar yuborilmoqda... (0/{len(users)})"
            )
            
            # Send broadcast
            success_count = 0
            fail_count = 0
            
            for i, user in enumerate(users):
                try:
                    await context.bot.send_message(
                        chat_id=user['chat_id'],
                        text=f"📢 *Admin xabari*\n\n{broadcast_text}",
                        parse_mode='Markdown'
                    )
                    success_count += 1
                except Exception:
                    fail_count += 1
                
                # Update status every 10 users
                if i % 10 == 0 and i > 0:
                    try:
                        await status_message.edit_text(
                            f"📨 Xabar yuborilmoqda... ({i}/{len(users)})"
                        )
                    except:
                        pass
            
            # Final status
            try:
                await status_message.edit_text(
                    f"✅ Xabar yuborish yakunlandi!\n\n"
                    f"✓ Muvaffaqiyatli: {success_count}\n"
                    f"✗ Muvaffaqiyatsiz: {fail_count}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
                )
            except Exception as e:
                logger.error(f"Error updating final status: {e}")
                # Try to send a new message if editing fails
                try:
                    await context.bot.send_message(
                        chat_id=query.message.chat_id,
                        text=f"✅ Xabar yuborish yakunlandi!\n\n"
                        f"✓ Muvaffaqiyatli: {success_count}\n"
                        f"✗ Muvaffaqiyatsiz: {fail_count}",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
                    )
                except:
                    pass
            
            # Reset state
            context.user_data.pop('admin_state', None)
            context.user_data.pop('broadcast_text', None)
        finally:
            cursor.close()
            conn.close()
    except Exception as e:
        logger.error(f"Error in confirm_broadcast: {e}")
        try:
            await query.edit_message_text(
                f"⚠️ Xabar yuborishda xatolik yuz berdi: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
            )
        except:
            # Try to send a new message if editing fails
            try:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text=f"⚠️ Xabar yuborishda xatolik yuz berdi: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data="admin_back")]])
                )
            except:
                pass

# Subscription check functions
async def check_user_subscribed(bot, user_id: int) -> Tuple[bool, List[Dict]]:
    """Check if user is subscribed to all required channels"""
    try:
        channels = db.get_all_required_channels()
        
        # If there are no required channels, consider the user as subscribed
        if not channels:
            return True, []
            
        not_subscribed = []
        
        for channel in channels:
            try:
                # Get the actual chat ID from the channel ID
                chat_id = channel['channel_id']
                
                # Get chat member status
                chat_member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
                
                # Debug log
                logger.info(f"User {user_id} status in channel {chat_id}: {chat_member.status}")
                
                # Check if user is a member, admin, or creator of the channel
                if chat_member.status not in ['member', 'administrator', 'creator']:
                    not_subscribed.append(channel)
            except Exception as e:
                logger.error(f"Error checking subscription for channel {channel['channel_id']}: {e}")
                # If there's an error, assume user is not subscribed
                not_subscribed.append(channel)
        
        # User is subscribed if not_subscribed list is empty
        return len(not_subscribed) == 0, not_subscribed
    except Exception as e:
        logger.error(f"Error in check_user_subscribed: {e}")
        # In case of error, assume user is not subscribed
        return False, []

async def send_subscription_message(update: Update, context: CallbackContext) -> bool:
    """Send message to user about required channel subscriptions"""
    user_id = update.effective_user.id
    
    try:
        is_subscribed, not_subscribed = await check_user_subscribed(context.bot, user_id)
        
        if is_subscribed:
            return True
        
        # Create keyboard with channel links
        keyboard = []
        for channel in not_subscribed:
            keyboard.append([InlineKeyboardButton(f"📢 {channel['channel_name']}", url=channel['channel_link'])])
        
        keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription")])
        
        # Send message
        await update.message.reply_text(
            "❗️ *Majburiy obuna*\n\n"
            "Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
        return False
    except Exception as e:
        logger.error(f"Error in send_subscription_message: {e}")
        # In case of error, allow user to continue
        return True

async def check_subscription_callback(update: Update, context: CallbackContext) -> None:
    """Handle subscription check callback"""
    query = update.callback_query
    user_id = query.from_user.id
    
    try:
        # Debug log
        logger.info(f"Checking subscription for user {user_id}")
        
        is_subscribed, not_subscribed = await check_user_subscribed(context.bot, user_id)
        
        # Debug log
        logger.info(f"User {user_id} subscription status: {is_subscribed}, not subscribed to: {len(not_subscribed)} channels")
        
        if is_subscribed:
            try:
                await query.answer("✅ Barcha kanallarga obuna bo'lgansiz!", show_alert=True)
            except Exception as e:
                logger.error(f"Error answering callback query: {e}")
            
            try:
                await query.delete_message()
            except Exception as e:
                logger.error(f"Error deleting message: {e}")
            
            # Continue with the original command if any
            if 'original_command' in context.user_data:
                original_command = context.user_data.pop('original_command')
                await context.bot.process_update(original_command)
        else:
            # Create keyboard with channel links
            keyboard = []
            for channel in not_subscribed:
                keyboard.append([InlineKeyboardButton(f"📢 {channel['channel_name']}", url=channel['channel_link'])])
            
            keyboard.append([InlineKeyboardButton("✅ Tekshirish", callback_data="check_subscription")])
            
            try:
                await query.answer("❌ Siz hali barcha kanallarga obuna bo'lmagansiz.", show_alert=True)
            except Exception as e:
                logger.error(f"Error answering callback query: {e}")
            
            try:
                await query.edit_message_text(
                    "❗️ *Majburiy obuna*\n\n"
                    "Botdan foydalanish uchun quyidagi kanallarga obuna bo'lishingiz kerak:",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Error editing message: {e}")
    except Exception as e:
        logger.error(f"Error in check_subscription_callback: {e}")
        try:
            await query.answer("Tekshirishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring.", show_alert=True)
        except:
            pass
