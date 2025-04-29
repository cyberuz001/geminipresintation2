import asyncio
import html
import json
import logging
import traceback
from datetime import datetime
import os
import sys
import random
from pathlib import Path

# Add parent directory to path to ensure imports work correctly
parent_dir = Path(__file__).parent.parent.resolve()
if str(parent_dir) not in sys.path:
    sys.path.append(str(parent_dir))

from bot.ai_generator import abstract
from bot.ai_generator import gemini_utils
from bot.ai_generator import presentation

from bot import config
from bot import database
from bot import admin

import telegram
from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    User,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackContext,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)


# setup
db = database.Database()
logger = logging.getLogger(__name__)

CHAT_MODES = config.chat_modes

HELP_MESSAGE = """Commands:
⚪ /menu – Show menu
⚪ /mode – Select mode
⚪ /premium – Premium status
⚪ /help – Show help
⚪ /admin – Admin panel (only for admins)
"""

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("/menu", "Show menu"),
        BotCommand("/mode", "Select mode"),
        BotCommand("/premium", "Premium status"),
        BotCommand("/help", "Show help"),
        BotCommand("/admin", "Admin panel (only for admins)"),
    ])


def split_text_into_chunks(text, chunk_size):
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


async def register_user_if_not_exists(update: Update, context: CallbackContext, user: User):
    if not db.check_if_user_exists(user.id):
        db.add_new_user(
            user.id,
            update.message.chat_id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name
        )


async def check_subscription_required(update: Update, context: CallbackContext):
    """Check if user is subscribed to required channels"""
    # Skip check for admins
    user_id = update.effective_user.id
    if db.is_admin(user_id):
        return True
    
    # Check subscription
    return await admin.send_subscription_message(update, context)


async def check_premium_limit(user_id: int, content_type: str) -> bool:
    """Check if user has reached their limit for presentations or abstracts
    
    Args:
        user_id: The user ID to check
        content_type: Either 'presentations_created' or 'abstracts_created'
        
    Returns:
        bool: True if user can create more content, False if they've reached their limit
    """
    # Admins have no limits
    if db.is_admin(user_id):
        return True
    
    # Premium users can create up to 15 items
    if db.is_premium(user_id):
        count = db.get_user_attribute(user_id, content_type)
        return count < 15
    
    # Regular users can create up to 1 item (changed from 2 to 1)
    count = db.get_user_attribute(user_id, content_type)
    return count < 1


async def check_expired_premium(context: CallbackContext) -> None:
    """Check for expired premium subscriptions and notify users"""
    try:
        # Get expired users and remove their premium status
        expired_users = db.remove_expired_premium()
        
        # Notify each user about their expired premium
        for user in expired_users:
            user_id = user['user_id']
            chat_id = db.get_user_attribute(user_id, "chat_id")
            
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="⚠️ *Premium obuna muddati tugadi*\n\n"
                         "Sizning premium obunangiz muddati tugadi. "
                         "Premium imkoniyatlardan foydalanish uchun obunani yangilang.\n\n"
                         f"Premium obuna sotib olish uchun admin bilan bog'laning: @{config.admin_username}",
                    parse_mode=ParseMode.MARKDOWN
                )
                logger.info(f"Notified user {user_id} about expired premium")
            except Exception as e:
                logger.error(f"Failed to notify user {user_id} about expired premium: {e}")
    except Exception as e:
        logger.error(f"Error in check_expired_premium: {e}")


async def start_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    # Check subscription
    if not await check_subscription_required(update, context):
        # Save original command to continue after subscription
        context.user_data['original_command'] = update
        return

    db.set_user_attribute(user_id, "last_interaction", datetime.now().isoformat())

    # Simple welcome message
    await update.message.reply_text("Salom! Men Gemini AI integratsiyasi bilan ishlangan botman 🤖\n\n" + HELP_MESSAGE)


async def help_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    
    # Check subscription
    if not await check_subscription_required(update, context):
        # Save original command to continue after subscription
        context.user_data['original_command'] = update
        return
    
    db.set_user_attribute(user_id, "last_interaction", datetime.now().isoformat())
    await update.message.reply_text(HELP_MESSAGE, parse_mode=ParseMode.HTML)


async def message_handle(update: Update, context: CallbackContext, message=None):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id

    db.set_user_attribute(user_id, "last_interaction", datetime.now().isoformat())


async def show_chat_modes_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    
    # Check subscription
    if not await check_subscription_required(update, context):
        # Save original command to continue after subscription
        context.user_data['original_command'] = update
        return
    
    db.set_user_attribute(user_id, "last_interaction", datetime.now().isoformat())

    keyboard = []
    for chat_mode, chat_mode_dict in CHAT_MODES.items():
        keyboard.append([InlineKeyboardButton(chat_mode_dict["name"], callback_data=f"set_chat_mode|{chat_mode}")])
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Chat rejimini tanlang:", reply_markup=reply_markup)


async def set_chat_mode_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    user_id = update.callback_query.from_user.id
    query = update.callback_query
    try:
        await query.answer()
    except Exception as e:
        logger.error(f"Error answering callback query: {e}")
    
    chat_mode = query.data.split("|")[1]
    db.set_user_attribute(user_id, "current_chat_mode", chat_mode)
    
    try:
        await query.edit_message_text(f"{CHAT_MODES[chat_mode]['welcome_message']}\n\n" + HELP_MESSAGE,
                                    parse_mode=ParseMode.HTML)
    except Exception as e:
        logger.error(f"Error editing message: {e}")


SELECTING_ACTION, SELECTING_MENU, INPUT_TOPIC, INPUT_PROMPT = map(chr, range(4))
END = ConversationHandler.END
PRESENTATION = "Presentation"
ABSTRACT = "Abstract"
# Tillar ro'yxatini o'zgartirish - Uzbek tilini birinchi o'ringa qo'yish
LANGUAGES = ['Uzbek', 'English', 'Russian', 'German', 'French', 'Italian', 'Spanish', 'Ukrainian', 'Polish', 'Turkish',
             'Romanian', 'Dutch', 'Greek', 'Czech', 'Portuguese', 'Swedish', 'Hungarian', 'Serbian', 'Bulgarian',
             'Danish', 'Norwegian', 'Finnish', 'Slovak', 'Croatian', 'Arabic', 'Hebrew', 'Lithuanian', 'Slovenian',
             'Bengali', 'Chinese', 'Persian', 'Indonesian', 'Latvian', 'Tamil', 'Japanese', 'Estonian', 'Telugu',
             'Korean', 'Thai', 'Icelandic', 'Vietnamese']
LANGUAGES_EMOJI = ['🇺🇿', '🇬🇧', '🏳️', '🇩🇪', '🇫🇷', '🇮🇹', '🇪🇸', '🇺🇦', '🇵🇱', '🇹🇷', '🇷🇴', '🇳🇱', '🇬🇷',
                   '🇨🇿', '🇵🇹', '🇸🇪', '🇭🇺', '🇷🇸', '🇧🇬', '🇩🇰', '🇳🇴', '🇫🇮', '🇸🇰', '🇭🇷', '🇸🇦',
                   '🇮🇱', '🇱🇹', '🇸🇮', '🇧🇩', '🇨🇳', '🇮🇷', '🇮🇩', '🇱🇻', '🇮🇳', '🇯🇵', '🇪🇪', '🇮🇳',
                   '🇰🇷', '🇹🇭', '🇮🇸', '🇻🇳']
TEMPLATES = ["Mountains", "Organic", "East Asia", "Explore", "3D Float", "Luminous", "Academic", "Snowflake", "Floral",
             "Minimal"]
TEMPLATES_EMOJI = ["🗻", "🌿", "🐼", "🧭", "🌑", "🕯️", "🎓", "❄️", "🌺", "◽"]
TYPES = ["Fun", "Serious", "Creative", "Informative", "Inspirational", "Motivational", "Educational", "Historical",
         "Romantic", "Mysterious", "Relaxing", "Adventurous", "Humorous", "Scientific", "Musical", "Horror", "Fantasy",
         "Action", "Dramatic", "Satirical", "Poetic", "Thriller", "Sports", "Comedy", "Biographical", "Political",
         "Magical", "Mystery", "Travel", "Documentary", "Crime", "Cooking"]
TYPES_EMOJI = ["😂", "😐", "🎨", "📚", "🌟", "💪", "👨‍🎓", "🏛️", "💕", "🕵️‍♂️", "🧘‍♀️", "🗺️", "🤣", "🔬", "🎵", "😱", "🦄",
               "💥", "😮", "🙃", "🌸", "😰", "⚽", "😆", "📜", "🗳️", "✨", "🔮", "✈️", "🎥", "🚓", "🍽️"]

# Taqdimot uchun slaydlar soni (oddiy foydalanuvchilar uchun max 12, premium uchun max 26)
SLIDE_COUNTS = [str(i) for i in range(3, 27)]
SLIDE_COUNTS_EMOJI = ["📊"] * 24  # Use the same emoji for all counts

# Abstrakt uchun sahifalar soni (oddiy foydalanuvchilar uchun uchun 2-6, premium uchun 2-15)
PAGE_COUNTS = [str(i) for i in range(2, 16)]
PAGE_COUNTS_EMOJI = ["📄"] * 14  # Use the same emoji for all page counts

PLAN_COUNTS = [str(i) for i in range(3, 11)]
PLAN_COUNTS_EMOJI = ["📋"] * 8  # Use the same emoji for all plan counts
BACK = "⬅️Orqaga"
(
    PRESENTATION_LANGUAGE_CHOICE,
    ABSTRACT_LANGUAGE_CHOICE,
    TEMPLATE_CHOICE,
    PRESENTATION_TYPE_CHOICE,
    ABSTRACT_TYPE_CHOICE,
    COUNT_SLIDE_CHOICE,
    PLAN_COUNT_CHOICE,
    ABSTRACT_PAGE_COUNT_CHOICE,
    TOPIC_CHOICE,
    API_RESPONSE,
    START_OVER,
    MESSAGE_ID,
) = map(chr, range(10, 22))


async def menu_handle(update: Update, context: CallbackContext) -> str:
    try:
        if hasattr(update, 'callback_query') and update.callback_query:
            await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
            user_id = update.callback_query.from_user.id
        else:
            await register_user_if_not_exists(update, context, update.message.from_user)
            user_id = update.message.from_user.id
            
            # Check subscription
            if not await check_subscription_required(update, context):
                # Save original command to continue after subscription
                context.user_data['original_command'] = update
                return ConversationHandler.END
            
            try:
                if MESSAGE_ID in context.chat_data:
                    await context.bot.delete_message(chat_id=update.effective_chat.id,
                                                    message_id=context.chat_data[MESSAGE_ID].message_id)
            except telegram.error.BadRequest:
                pass
            except Exception as e:
                logger.error(f"Error in menu_handle: {e}")
    except Exception as e:
        logger.error(f"Error in menu_handle: {e}")

    keyboard = [
        [
            InlineKeyboardButton(f"💻Taqdimot", callback_data=PRESENTATION)
        ],
        [
            InlineKeyboardButton(f"📝Abstrakt", callback_data=ABSTRACT)
        ]
    ]
    
    try:
        if context.user_data.get(START_OVER):
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("Menyu:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            # Simple text message instead of animation
            context.chat_data[MESSAGE_ID] = await update.message.reply_text("Menyu:",
                                                                        reply_markup=InlineKeyboardMarkup(keyboard))
        context.user_data[START_OVER] = False
        return SELECTING_ACTION
    except Exception as e:
        logger.error(f"Error showing menu: {e}")
        await update.message.reply_text("Menyu ko'rsatishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring.")
        return ConversationHandler.END


async def generate_keyboard(page, word_array, emoji_array, callback):
    keyboard = []
    per_page = 12
    for i, words in enumerate(word_array[(page-1)*per_page:page*per_page]):
        if i % 2 == 0:
            keyboard.append([InlineKeyboardButton(emoji_array[i+((page-1)*per_page)] + words,
                                                  callback_data=f"{callback}{words}")])
        else:
            keyboard[-1].append(InlineKeyboardButton(emoji_array[i+((page-1)*per_page)] + words,
                                                     callback_data=f"{callback}{words}"))
    if len(word_array) > per_page and page == 1:
        keyboard.append([InlineKeyboardButton(">>", callback_data=f"page_{callback}{page+1}")])
    elif page != 1:
        if len(word_array) > page*per_page:
            keyboard.append([
                InlineKeyboardButton("<<", callback_data=f"page_{callback}{page-1}"),
                InlineKeyboardButton(">>", callback_data=f"page_{callback}{page+1}")
            ])
        else:
            keyboard.append([InlineKeyboardButton("<<", callback_data=f"page_{callback}{page-1}")])
    keyboard.append([InlineKeyboardButton(text=BACK, callback_data=str(END))])
    return InlineKeyboardMarkup(keyboard)


async def presentation_language_callback(update: Update, context: CallbackContext) -> str:
    try:
        await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
        user_id = update.callback_query.from_user.id
        
        # Check if user has reached their presentation limit
        if not await check_premium_limit(user_id, "presentations_created"):
            # User has reached their limit
            is_premium = db.is_premium(user_id)
            if is_premium:
                await update.callback_query.answer("Siz premium foydalanuvchi uchun maksimal miqdorga yetdingiz (15 ta taqdimot).", show_alert=True)
            else:
                await update.callback_query.edit_message_text(
                    "⚠️ Siz oddiy foydalanuvchi uchun maksimal miqdorga yetdingiz (1 ta taqdimot).\n\n"
                    "Premium obuna sotib olish uchun admin bilan bog'laning: "
                    f"@{config.admin_username}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data=str(END))]])
                )
            return SELECTING_ACTION
        
        # Check subscription
        is_subscribed, not_subscribed = await admin.check_user_subscribed(context.bot, user_id)
        if not is_subscribed and not db.is_admin(user_id):
            await admin.check_subscription_callback(update, context)
            return SELECTING_ACTION
        
        query = update.callback_query
        data = query.data
        page = 1
        if data.startswith("page_language_"):
            page = int(data.replace("page_language_", ""))
        text = "Taqdimot tilini tanlang:"
        reply_markup = await generate_keyboard(page, LANGUAGES, LANGUAGES_EMOJI, "language_")
        await query.answer()
        await query.edit_message_text(text=text, reply_markup=reply_markup)
        return SELECTING_MENU
    except Exception as e:
        logger.error(f"Error in presentation_language_callback: {e}")
        await update.callback_query.answer("Xatolik yuz berdi")
        return ConversationHandler.END


async def abstract_language_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    user_id = update.callback_query.from_user.id
    
    # Check if user has reached their abstract limit
    if not await check_premium_limit(user_id, "abstracts_created"):
        # User has reached their limit
        is_premium = db.is_premium(user_id)
        if is_premium:
            await update.callback_query.answer("Siz premium foydalanuvchi uchun maksimal miqdorga yetdingiz (15 ta abstrakt).", show_alert=True)
        else:
            await update.callback_query.edit_message_text(
                "⚠️ Siz oddiy foydalanuvchi uchun maksimal miqdorga yetdingiz (1 ta abstrakt).\n\n"
                "Premium obuna sotib olish uchun admin bilan bog'laning: "
                f"@{config.admin_username}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Orqaga", callback_data=str(END))]])
            )
        return SELECTING_ACTION
    
    # Check subscription
    is_subscribed, not_subscribed = await admin.check_user_subscribed(context.bot, user_id)
    if not is_subscribed and not db.is_admin(user_id):
        await admin.check_subscription_callback(update, context)
        return SELECTING_ACTION
    
    query = update.callback_query
    data = query.data
    page = 1
    if data.startswith("page_language_"):
        page = int(data.replace("page_language_", ""))
    text = "Abstrakt tilini tanlang:"
    reply_markup = await generate_keyboard(page, LANGUAGES, LANGUAGES_EMOJI, "language_")
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return SELECTING_MENU


async def presentation_template_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    page = 1
    if data.startswith("page_template_"):
        page = int(data.replace("page_template_", ""))
    else:
        context.user_data[PRESENTATION_LANGUAGE_CHOICE] = data
    text = "Taqdimot shablonini tanlang:"
    reply_markup = await generate_keyboard(page, TEMPLATES, TEMPLATES_EMOJI, "template_")
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return SELECTING_MENU


async def presentation_type_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    page = 1
    if data.startswith("page_type_"):
        page = int(data.replace("page_type_", ""))
    else:
        context.user_data[TEMPLATE_CHOICE] = data
    text = "Taqdimot turini tanlang:"
    reply_markup = await generate_keyboard(page, TYPES, TYPES_EMOJI, "type_")
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return SELECTING_MENU


async def abstract_type_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    page = 1
    if data.startswith("page_type_"):
        page = int(data.replace("page_type_", ""))
    else:
        context.user_data[ABSTRACT_LANGUAGE_CHOICE] = data
    text = "Abstrakt turini tanlang:"
    reply_markup = await generate_keyboard(page, TYPES, TYPES_EMOJI, "type_")
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return SELECTING_MENU


async def presentation_slide_count_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    user_id = update.callback_query.from_user.id
    page = 1
    
    if data.startswith("page_slide_count_"):
        page = int(data.replace("page_slide_count_", ""))
    else:
        context.user_data[PRESENTATION_TYPE_CHOICE] = data
    
    text = "Taqdimot uchun taxminiy slaydlar sonini tanlang:"
    
    # Oddiy foydalanuvchilar uchun max 12 slide, premium uchun max 26
    is_premium = db.is_premium(user_id) or db.is_admin(user_id)
    max_slides = 26 if is_premium else 12
    available_counts = SLIDE_COUNTS[:max_slides-2]  # 3 dan max_slides gacha
    
    reply_markup = await generate_keyboard(page, available_counts, SLIDE_COUNTS_EMOJI[:len(available_counts)], "slide_count_")
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return SELECTING_MENU


async def abstract_page_count_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    user_id = update.callback_query.from_user.id
    page = 1
    
    if data.startswith("page_page_count_"):
        page = int(data.replace("page_page_count_", ""))
    else:
        context.user_data[ABSTRACT_TYPE_CHOICE] = data
    
    text = "Abstrakt uchun sahifalar sonini tanlang:"
    
    # Oddiy foydalanuvchilar uchun 2-6 page, premium uchun 2-15
    is_premium = db.is_premium(user_id) or db.is_admin(user_id)
    max_pages = 15 if is_premium else 6
    available_counts = PAGE_COUNTS[:max_pages-1]  # 2 dan max_pages gacha
    
    reply_markup = await generate_keyboard(page, available_counts, PAGE_COUNTS_EMOJI[:len(available_counts)], "page_count_")
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return SELECTING_MENU


async def presentation_plan_count_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    page = 1
    if data.startswith("page_plan_count_"):
        page = int(data.replace("page_plan_count_", ""))
    else:
        context.user_data[COUNT_SLIDE_CHOICE] = data
    text = "Taqdimot rejasi uchun nechta punkt bo'lishini tanlang:"
    reply_markup = await generate_keyboard(page, PLAN_COUNTS, PLAN_COUNTS_EMOJI, "plan_count_")
    await query.answer()
    await query.edit_message_text(text=text, reply_markup=reply_markup)
    return SELECTING_MENU


async def presentation_topic_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    text = "Taqdimot mavzusi nima?"
    context.user_data[PLAN_COUNT_CHOICE] = data
    await query.answer()
    await query.edit_message_text(text=text)
    if MESSAGE_ID in context.chat_data:
        del context.chat_data[MESSAGE_ID]
    return INPUT_TOPIC


async def abstract_topic_callback(update: Update, context: CallbackContext) -> str:
    await register_user_if_not_exists(update.callback_query, context, update.callback_query.from_user)
    query = update.callback_query
    data = query.data
    text = "Abstrakt mavzusi nima?"
    context.user_data[ABSTRACT_PAGE_COUNT_CHOICE] = data
    await query.answer()
    await query.edit_message_text(text=text)
    if MESSAGE_ID in context.chat_data:
        del context.chat_data[MESSAGE_ID]
    return INPUT_TOPIC


async def auto_generate_presentation(update: Update, context: CallbackContext, user_id, message_id, prompt, template_choice):
    # Simple notification message
    notification_message = await update.message.reply_text("⌛ Tayyorlanmoqda...")
    
    try:
        logger.info(f"Generating presentation with prompt: {prompt[:100]}...")
        
        # Get queue status
        queue_status = await gemini_utils.get_queue_status()
        queue_size = queue_status["queue_size"]
        
        # If queue is getting large, inform the user
        if queue_size > 5:
            await notification_message.edit_text(
                f"⌛ So'rovingiz navbatga qo'shildi. Hozirgi navbat: {queue_size} ta so'rov.\n"
                f"Iltimos, kuting..."
            )
        
        # Add request to queue with priority based on user type (admin/premium/regular)
        priority = 1 if db.is_admin(user_id) else (2 if db.is_premium(user_id) else 3)
        
        # Process the prompt through the queue system
        response, n_used_tokens = await gemini_utils.process_prompt(prompt, priority=priority)
        
        logger.info(f"Presentation generated successfully, tokens used: {n_used_tokens}")
    except OverflowError as e:
        logger.error(f"Overflow error: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="Tizim hozir band. Iltimos, qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)
        return END
    except TimeoutError as e:
        logger.error(f"Timeout error: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="So'rov vaqti tugadi. Iltimos, keyinroq qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)
        return END
    except RuntimeError as e:
        logger.error(f"Runtime error: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="Xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)
        return END
    except ValueError as e:
        logger.error(f"Value error: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="Sizning taqdimotingiz juda katta. Iltimos, qayta urinib ko'ring 😊",
                                      reply_to_message_id=message_id)
        return END
    except Exception as e:
        logger.error(f"Unexpected error in auto_generate_presentation: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="Kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)
        return END
      
    try:
        # Increment the presentations counter for the user
        db.increment_user_counter(user_id, "presentations_created")
        
        # Update notification message
        await notification_message.edit_text("⌛ Taqdimot yaratilmoqda...")
        
        logger.info(f"Generating PPT with template: {template_choice}")
        pptx_bytes, pptx_title = await presentation.generate_ppt(response, template_choice)
        logger.info(f"PPT generated successfully: {pptx_title}")
        
        # Success message
        await update.message.reply_text(f"✅ Taqdimot muvaffaqiyatli yaratildi: {pptx_title}")
        
        await update.message.reply_document(document=pptx_bytes, filename=pptx_title)
        await notification_message.delete()
    except Exception as e:
        logger.error(f"Error in final stage of auto_generate_presentation: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="Taqdimot yaratishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)
        return END


async def presentation_save_input(update: Update, context: CallbackContext):
    if update.edited_message is not None:
        return
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_data = context.user_data
    user_id = update.message.from_user.id
    message_id = update.message.message_id
    topic_choice = update.message.text
    
    try:
        user_mode = db.get_user_attribute(user_id, "current_chat_mode")
        language_choice = user_data[PRESENTATION_LANGUAGE_CHOICE].replace("language_", "")
        template_choice = user_data[TEMPLATE_CHOICE].replace("template_", "")
        type_choice = user_data[PRESENTATION_TYPE_CHOICE].replace("type_", "")
        count_slide_choice = user_data[COUNT_SLIDE_CHOICE].replace("slide_count_", "")
        plan_count_choice = user_data[PLAN_COUNT_CHOICE].replace("plan_count_", "")
        
        logger.info(f"Generating presentation prompt for topic: {topic_choice} with {plan_count_choice} plan points")
        prompt = await presentation.generate_ppt_prompt(language_choice, type_choice, count_slide_choice, topic_choice, plan_count_choice)
        
        if user_mode == "auto":
            # Check if user can create more presentations
            if await check_premium_limit(user_id, "presentations_created"):
                loop = asyncio.get_event_loop()
                loop.create_task(auto_generate_presentation(update, context, user_id, message_id, prompt, template_choice))
            else:
                is_premium = db.is_premium(user_id)
                if is_premium:
                    await update.message.reply_text("Siz premium foydalanuvchi uchun maksimal miqdorga yetdingiz (15 ta taqdimot).")
                else:
                    await update.message.reply_text(
                        "⚠️ Siz oddiy foydalanuvchi uchun maksimal miqdorga yetdingiz (1 ta taqdimot).\n\n"
                        "Premium obuna sotib olish uchun admin bilan bog'laning: "
                        f"@{config.admin_username}"
                    )
        else:
            try:
                await update.message.reply_text(text="`" + prompt + "`", parse_mode=ParseMode.MARKDOWN_V2)
            except telegram.error.BadRequest:
                await update.message.reply_text("Ma'lumotlarni tekshiring va mavzuni qayta kiriting 😊")
                return INPUT_TOPIC
            await update.message.reply_text(
                text="1) Oldingi xabardagi so'rovni nusxalang va qayta ishlang 😊\n"
                     "2) Qayta ishlangan so'rovning javobini nusxalang va chatga joylashtiring 😊\n\n"
                     "Tavsiya etilgan veb-saytlar:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(text='Google Gemini', url='https://gemini.google.com/')],
                    [InlineKeyboardButton(text='Bard', url='https://bard.google.com/')],
                ])
            )
            return INPUT_PROMPT
    except Exception as e:
        logger.error(f"Error in presentation_save_input: {str(e)}")
        await update.message.reply_text("Xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊")
        return END
    return END


async def auto_generate_abstract(update: Update, context: CallbackContext, user_id, message_id, prompt, page_count):
    notification_message = await update.message.reply_text("⌛ Tayyorlanmoqda...")
    
    try:
        logger.info(f"Generating abstract with prompt: {prompt[:100]}...")
        
        # Get queue status
        queue_status = await gemini_utils.get_queue_status()
        queue_size = queue_status["queue_size"]
        
        # If queue is getting large, inform the user
        if queue_size > 5:
            await notification_message.edit_text(
                f"⌛ So'rovingiz navbatga qo'shildi. Hozirgi navbat: {queue_size} ta so'rov.\n"
                f"Iltimos, kuting..."
            )
        
        # Add request to queue with priority based on user type
        priority = 1 if db.is_admin(user_id) else (2 if db.is_premium(user_id) else 3)
        
        # Process the prompt through the queue system
        response, n_used_tokens = await gemini_utils.process_prompt(prompt, priority=priority)
        
        logger.info(f"Abstract generated successfully, tokens used: {n_used_tokens}")
    except OverflowError:
        await notification_message.delete()
        await update.message.reply_text(text="Tizim hozir band. Iltimos, qayta urinib ko'ring 😊",
                                      reply_to_message_id=message_id)
        return END
    except TimeoutError:
        await notification_message.delete()
        await update.message.reply_text(text="So'rov vaqti tugadi. Iltimos, keyinroq qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)
        return END
    except RuntimeError:
        await notification_message.delete()
        await update.message.reply_text(text="Xatolik yuz berdi. Iltimos, qayta urinib ko'ring 😊",
                                      reply_to_message_id=message_id)
        return END
    except ValueError:
        await notification_message.delete()
        await update.message.reply_text(text="Sizning abstraktingiz juda katta. Iltimos, qayta urinib ko'ring 😊",
                                      reply_to_message_id=message_id)
        return END
    except Exception as e:
        logger.error(f"Unexpected error in auto_generate_abstract: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="Kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)
        return END
      
    # Increment the abstracts counter for the user
    db.increment_user_counter(user_id, "abstracts_created")
    
    # Update notification message
    await notification_message.edit_text("⌛ Abstrakt yaratilmoqda...")
    
    try:
        # Pass the page_count parameter to generate_docx
        docx_bytes, docx_title = await abstract.generate_docx(response, page_count)
        
        # Success message
        await update.message.reply_text(f"✅ Abstrakt muvaffaqiyatli yaratildi: {docx_title}")
        
        await update.message.reply_document(document=docx_bytes, filename=docx_title)
        await notification_message.delete()
    except Exception as e:
        logger.error(f"Error generating abstract document: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text(text="Abstrakt yaratishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊",
                                      reply_to_message_id=message_id)


async def abstract_save_input(update: Update, context: CallbackContext):
    if update.edited_message is not None:
        return
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_data = context.user_data
    user_id = update.message.from_user.id
    message_id = update.message.message_id
    topic_choice = update.message.text
    user_mode = db.get_user_attribute(user_id, "current_chat_mode")
    language_choice = user_data[ABSTRACT_LANGUAGE_CHOICE].replace("language_", "")
    type_choice = user_data[ABSTRACT_TYPE_CHOICE].replace("type_", "")
    page_count = user_data[ABSTRACT_PAGE_COUNT_CHOICE].replace("page_count_", "")
    
    prompt = await abstract.generate_docx_prompt(language_choice, type_choice, topic_choice, page_count)
    
    if user_mode == "auto":
        # Check if user can create more abstracts
        if await check_premium_limit(user_id, "abstracts_created"):
            loop = asyncio.get_event_loop()
            loop.create_task(auto_generate_abstract(update, context, user_id, message_id, prompt, page_count))
        else:
            is_premium = db.is_premium(user_id)
            if is_premium:
                await update.message.reply_text("Siz premium foydalanuvchi uchun maksimal miqdorga yetdingiz (15 ta abstrakt).")
            else:
                await update.message.reply_text(
                    "⚠️ Siz oddiy foydalanuvchi uchun maksimal miqdorga yetdingiz (1 ta abstrakt).\n\n"
                    "Premium obuna sotib olish uchun admin bilan bog'laning: "
                    f"@{config.admin_username}"
                )
    else:
        try:
            await update.message.reply_text(text="`" + prompt + "`", parse_mode=ParseMode.MARKDOWN_V2)
        except telegram.error.BadRequest:
            await update.message.reply_text("Ma'lumotlarni tekshiring va mavzuni qayta kiriting 😊")
            return INPUT_TOPIC
        await update.message.reply_text(
            text="1) Oldingi xabardagi so'rovni nusxalang va qayta ishlang 😊\n"
                 "2) Qayta ishlangan so'rovning javobini nusxalang va chatga joylashtiring 😊\n\n"
                 "Tavsiya etilgan veb-saytlar:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(text='Google Gemini', url='https://gemini.google.com/')],
                [InlineKeyboardButton(text='Bard', url='https://bard.google.com/')],
            ])
        )
        return INPUT_PROMPT
    return END


async def presentation_prompt_callback(update: Update, context: CallbackContext):
    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return
    await register_user_if_not_exists(update, context, update.message.from_user)
    api_response = update.message.text
    user_data = context.user_data
    user_id = update.message.from_user.id
    template_choice = user_data[TEMPLATE_CHOICE].replace("template_", "")
    
    # Check if user can create more presentations
    if not await check_premium_limit(user_id, "presentations_created"):
        is_premium = db.is_premium(user_id)
        if is_premium:
            await update.message.reply_text("Siz premium foydalanuvchi uchun maksimal miqdorga yetdingiz (15 ta taqdimot).")
        else:
            await update.message.reply_text(
                "⚠️ Siz oddiy foydalanuvchi uchun maksimal miqdorga yetdingiz (1 ta taqdimot).\n\n"
                "Premium obuna sotib olish uchun admin bilan bog'laning: "
                f"@{config.admin_username}"
            )
        return END
    
    # Simple notification message
    notification_message = await update.message.reply_text("⌛ Tayyorlanmoqda...")
    
    try:
        # Increment the presentations counter for the user
        db.increment_user_counter(user_id, "presentations_created")
        
        pptx_bytes, pptx_title = await presentation.generate_ppt(api_response, template_choice)
        
        # Success message
        await update.message.reply_text(f"✅ Taqdimot muvaffaqiyatli yaratildi: {pptx_title}")
        
        await update.message.reply_document(document=pptx_bytes, filename=pptx_title)
        await notification_message.delete()
    except IndexError:
        await notification_message.delete()
        await update.message.reply_text("Ma'lumotlarni tekshiring va qayta urinib ko'ring 😊")
        return INPUT_PROMPT
    except Exception as e:
        logger.error(f"Error in presentation_prompt_callback: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text("Taqdimot yaratishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊")
        return INPUT_PROMPT
    return END


async def abstract_prompt_callback(update: Update, context: CallbackContext):
    if update.edited_message is not None:
        await edited_message_handle(update, context)
        return
    await register_user_if_not_exists(update, context, update.message.from_user)
    api_response = update.message.text
    user_data = context.user_data
    user_id = update.message.from_user.id
    page_count = user_data[ABSTRACT_PAGE_COUNT_CHOICE].replace("page_count_", "")
    
    # Check if user can create more abstracts
    if not await check_premium_limit(user_id, "abstracts_created"):
        is_premium = db.is_premium(user_id)
        if is_premium:
            await update.message.reply_text("Siz premium foydalanuvchi uchun maksimal miqdorga yetdingiz (15 ta abstrakt).")
        else:
            await update.message.reply_text(
                "⚠️ Siz oddiy foydalanuvchi uchun maksimal miqdorga yetdingiz (1 ta abstrakt).\n\n"
                "Premium obuna sotib olish uchun admin bilan bog'laning: "
                f"@{config.admin_username}"
            )
        return END
    
    # Simple notification message
    notification_message = await update.message.reply_text("⌛ Tayyorlanmoqda...")
    
    try:
        # Increment the abstracts counter for the user
        db.increment_user_counter(user_id, "abstracts_created")
        
        docx_bytes, docx_title = await abstract.generate_docx(api_response, page_count)
        
        # Success message
        await update.message.reply_text(f"✅ Abstrakt muvaffaqiyatli yaratildi: {docx_title}")
        
        await update.message.reply_document(document=docx_bytes, filename=docx_title)
        await notification_message.delete()
    except IndexError:
        await notification_message.delete()
        await update.message.reply_text("Ma'lumotlarni tekshiring va qayta urinib ko'ring 😊")
        return INPUT_PROMPT
    except Exception as e:
        logger.error(f"Error in abstract_prompt_callback: {str(e)}")
        await notification_message.delete()
        await update.message.reply_text("Abstrakt yaratishda xatolik yuz berdi. Iltimos, qayta urinib ko'ring. 😊")
        return INPUT_PROMPT
    return END


async def end_second_level(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Return to top level conversation."""
    context.user_data[START_OVER] = True
    await menu_handle(update, context)
    return END


async def premium_status_handle(update: Update, context: CallbackContext):
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    
    # Check subscription
    if not await check_subscription_required(update, context):
        # Save original command to continue after subscription
        context.user_data['original_command'] = update
        return

    db.set_user_attribute(user_id, "last_interaction", datetime.now().isoformat())

    # Get user's premium status and usage
    is_premium = db.is_premium(user_id)
    presentations_created = db.get_user_attribute(user_id, "presentations_created")
    abstracts_created = db.get_user_attribute(user_id, "abstracts_created")
    
    # For admins, show special status
    if db.is_admin(user_id):
        text = f"🟢 <b>Admin</b> sifatida sizda cheksiz imkoniyatlar mavjud\n\n"
        text += f"Siz jami <b>{presentations_created}</b> ta taqdimot va <b>{abstracts_created}</b> ta abstrakt yaratdingiz"
    elif is_premium:
        # Get premium expiry date
        premium_expiry = db.get_premium_expiry(user_id)
        expiry_text = ""
        
        if premium_expiry:
            try:
                expiry_date = datetime.fromisoformat(premium_expiry)
                days_left = (expiry_date - datetime.now()).days
                expiry_display = expiry_date.strftime("%d.%m.%Y")
                
                if days_left > 0:
                    expiry_text = f"\nPremium obuna muddati: <b>{expiry_display}</b> ({days_left} kun qoldi)"
                else:
                    expiry_text = f"\nPremium obuna muddati: <b>Bugun tugaydi</b>"
            except Exception as e:
                logger.error(f"Error formatting premium expiry: {e}")
        
        text = f"👑 Siz <b>Premium</b> obunachisiz{expiry_text}\n\n"
        text += f"Siz <b>{presentations_created}/15</b> ta taqdimot va <b>{abstracts_created}/15</b> ta abstrakt yaratdingiz\n\n"
        text += f"Premium imkoniyatlar:\n"
        text += f"• Taqdimot: <b>26</b> tagacha slayd\n"
        text += f"• Abstrakt: <b>15</b> tagacha sahifa"
    else:
        text = f"⚪ Siz oddiy foydalanuvchisiz\n\n"
        text += f"Siz <b>{presentations_created}/1</b> ta taqdimot va <b>{abstracts_created}/1</b> ta abstrakt yaratdingiz\n\n"
        text += f"Oddiy foydalanuvchi imkoniyatlari:\n"
        text += f"• Taqdimot: <b>12</b> tagacha slayd\n"
        text += f"• Abstrakt: <b>6</b> tagacha sahifa\n\n"
        text += f"Premium obuna sotib olish uchun admin bilan bog'laning: @{config.admin_username}"

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def edited_message_handle(update: Update, context: CallbackContext):
    text = "🥲 Afsuski, xabarni <b>tahrirlash</b> qo'llab-quvvatlanmaydi"
    await update.edited_message.reply_text(text, parse_mode=ParseMode.HTML)


async def error_handle(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    
    # Check if update is None or doesn't have effective_chat
    if update is None or not hasattr(update, 'effective_chat') or update.effective_chat is None:
        logger.error(f"Error occurred with no chat context: {str(context.error)}")
        return
    
    # send error to the chat for test
    try:
        # collect error message
        tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
        tb_string = "".join(tb_list)
        
        # Foydalanuvchiga ko'rsatiladigan xabar
        user_message = "Xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
        
        # Timeout xatoligi uchun maxsus xabar
        if isinstance(context.error, TimeoutError) or "timeout" in str(context.error).lower():
            user_message = "Serverga ulanishda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring."
        
        # Foydalanuvchiga xabarni yuborish
        await context.bot.send_message(update.effective_chat.id, user_message)
        
        # Admin uchun to'liq xatolik ma'lumotini yuborish
        if db.is_admin(update.effective_user.id):
            update_str = update.to_dict() if isinstance(update, Update) else str(update)
            message = (
                f"Yangilanishni qayta ishlashda istisno yuz berdi\n"
                f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}"
                "</pre>\n\n"
                f"<pre>{html.escape(tb_string)}</pre>"
            )

            # split text into multiple messages due to 4096 character limit
            for message_chunk in split_text_into_chunks(message, 4096):
                try:
                    await context.bot.send_message(update.effective_chat.id, message_chunk, parse_mode=ParseMode.HTML)
                except telegram.error.BadRequest:
                    # answer has invalid characters, so we send it without parse_mode
                    await context.bot.send_message(update.effective_chat.id, message_chunk)
    except Exception as e:
        logger.error(f"Error in error_handle: {str(e)}")


async def admin_command_handler(update: Update, context: CallbackContext):
    """Handle the /admin command"""
    await admin.admin_command(update, context)


async def admin_callback_handler(update: Update, context: CallbackContext):
    """Handle admin panel callbacks"""
    await admin.admin_callback_handler(update, context)


async def admin_message_handler(update: Update, context: CallbackContext):
    """Handle admin panel messages"""
    user_id = update.effective_user.id
    
    if not db.is_admin(user_id):
        return
    
    if 'admin_state' not in context.user_data:
        return
    
    admin_state = context.user_data['admin_state']
    
    if admin_state == 'waiting_for_admin_id':
        await admin.add_admin(update, context)
    elif admin_state == 'waiting_for_premium_id':
        await admin.add_premium(update, context)
    elif admin_state == 'waiting_for_channel_info':
        await admin.add_channel(update, context)
    elif admin_state == 'waiting_for_broadcast':
        await admin.broadcast_message(update, context)


async def check_subscription_callback_handler(update: Update, context: CallbackContext):
    """Handle subscription check callback"""
    await admin.check_subscription_callback(update, context)

# Qo'shimcha funksiya qo'shish
async def queue_status_handle(update: Update, context: CallbackContext):
    """Handle the /queue command to show queue status"""
    await register_user_if_not_exists(update, context, update.message.from_user)
    user_id = update.message.from_user.id
    
    # Faqat adminlar uchun
    if not db.is_admin(user_id):
        await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
        return
    
    # Navbat holatini olish
    queue_status = await gemini_utils.get_queue_status()
    
    # Holat haqida xabar
    status_text = (
        f"📊 <b>Navbat holati:</b>\n\n"
        f"📝 Navbatdagi so'rovlar: <b>{queue_status['queue_size']}</b>/{queue_status['max_queue_size']}\n"
        f"⚙️ Ishchi holati: <b>{'Ishlamoqda' if queue_status['worker_running'] else 'To\'xtagan'}</b>\n"
        f"🔄 Kutilayotgan natijalar: <b>{queue_status['pending_results']}</b>"
    )
    
    await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)


def create_application() -> Application:
    """Create the Application and return it."""
    application = (
        ApplicationBuilder()
        .token(config.telegram_token)
        .concurrent_updates(True)
        .post_init(post_init)
        .build()
    )

    # Schedule job to check expired premium subscriptions (every 12 hours)
    application.job_queue.run_repeating(check_expired_premium, interval=43200, first=10)

    # add handlers
    if len(config.allowed_telegram_usernames) == 0:
        user_filter = filters.ALL
    else:
        user_filter = filters.User(username=config.allowed_telegram_usernames)

    application.add_handler(CommandHandler("start", start_handle, filters=user_filter))
    application.add_handler(CommandHandler("help", help_handle, filters=user_filter))
    application.add_handler(CommandHandler("queue", queue_status_handle, filters=user_filter))  # New command

    application.add_handler(MessageHandler(filters.COMMAND & user_filter, message_handle), group=2)

    application.add_handler(CommandHandler("mode", show_chat_modes_handle, filters=user_filter))
    application.add_handler(CallbackQueryHandler(set_chat_mode_handle, pattern="^set_chat_mode"))
    
    # Premium status handler
    application.add_handler(CommandHandler("premium", premium_status_handle, filters=user_filter))
    
    # Admin handlers
    application.add_handler(CommandHandler("admin", admin_command_handler, filters=user_filter))
    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_message_handler), group=3)
    
    # Subscription check handler
    application.add_handler(CallbackQueryHandler(check_subscription_callback_handler, pattern="^check_subscription$"))

    # Broadcast confirmation handler
    application.add_handler(CallbackQueryHandler(admin.confirm_broadcast, pattern="^admin_confirm_broadcast$"))
    
    presentation_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(presentation_language_callback, pattern=f"^{PRESENTATION}$")],
        states={
            SELECTING_MENU: [
                CallbackQueryHandler(presentation_language_callback, pattern="^page_language_"),
                CallbackQueryHandler(presentation_template_callback, pattern="^language_"),
                CallbackQueryHandler(presentation_template_callback, pattern="^page_template_"),
                CallbackQueryHandler(presentation_type_callback, pattern="^template_"),
                CallbackQueryHandler(presentation_type_callback, pattern="^page_type_"),
                CallbackQueryHandler(presentation_slide_count_callback, pattern="^type_"),
                CallbackQueryHandler(presentation_slide_count_callback, pattern="^page_slide_count_"),
                CallbackQueryHandler(presentation_plan_count_callback, pattern="^slide_count_"),
                CallbackQueryHandler(presentation_plan_count_callback, pattern="^page_plan_count_"),
                CallbackQueryHandler(presentation_topic_callback, pattern="^plan_count_"),
                             ],
            INPUT_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, presentation_save_input)],
            INPUT_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, presentation_prompt_callback)],
        },
        fallbacks=[
            CallbackQueryHandler(end_second_level, pattern=f"^{str(END)}$"),
            CommandHandler("menu", menu_handle, filters=user_filter)
        ],
        map_to_parent={
            END: SELECTING_ACTION,
            SELECTING_ACTION: SELECTING_ACTION,
        },
        allow_reentry=True,
    )

    abstract_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(abstract_language_callback, pattern=f"^{ABSTRACT}$")],
        states={
            SELECTING_MENU: [
                CallbackQueryHandler(abstract_language_callback, pattern="^page_language_"),
                CallbackQueryHandler(abstract_type_callback, pattern="^language_"),
                CallbackQueryHandler(abstract_type_callback, pattern="^page_type_"),
                CallbackQueryHandler(abstract_page_count_callback, pattern="^type_"),
                CallbackQueryHandler(abstract_page_count_callback, pattern="^page_page_count_"),
                CallbackQueryHandler(abstract_topic_callback, pattern="^page_count_")
                             ],
            INPUT_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, abstract_save_input)],
            INPUT_PROMPT: [MessageHandler(filters.TEXT & ~filters.COMMAND, abstract_prompt_callback)],
        },
        fallbacks=[
            CallbackQueryHandler(end_second_level, pattern=f"^{str(END)}$"),
            CommandHandler("menu", menu_handle, filters=user_filter)
        ],
        map_to_parent={
            END: SELECTING_ACTION,
            SELECTING_ACTION: SELECTING_ACTION,
        },
        allow_reentry=True,
    )

    selection_handlers = [
        presentation_conv,
        abstract_conv,
    ]

    menu_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("menu", menu_handle, filters=user_filter)],
        states={
            SELECTING_ACTION: selection_handlers,
        },
        fallbacks=[
            CommandHandler("menu", menu_handle, filters=user_filter)
        ],
    )
    application.add_handler(menu_conv_handler)

    application.add_error_handler(error_handle)
    
    return application


def run_bot() -> None:
    """Run the bot."""
    # Create the Application
    application = create_application()
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling()
