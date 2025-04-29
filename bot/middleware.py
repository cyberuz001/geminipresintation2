import logging
from functools import wraps
from typing import Callable, List, Optional, Set, Union

from telegram import Update
from telegram.ext import CallbackContext

from bot.admin import check_user_subscribed, send_subscription_message
from bot.database import Database

logger = logging.getLogger(__name__)
db = Database()

def admin_required(func):
    """Admin huquqini tekshirish uchun dekorator"""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        
        if not db.is_admin(user_id):
            if update.callback_query:
                await update.callback_query.answer("Bu amal faqat adminlar uchun.", show_alert=True)
            else:
                await update.message.reply_text("Bu buyruq faqat adminlar uchun.")
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapped

def subscription_required(func):
    """Majburiy obunani tekshirish uchun dekorator"""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Adminlar uchun tekshirish o'tkazilmaydi
        if db.is_admin(user_id):
            return await func(update, context, *args, **kwargs)
        
        # Foydalanuvchi obuna bo'lganligini tekshirish
        is_subscribed, _ = await check_user_subscribed(context.bot, user_id)
        
        if not is_subscribed:
            # Obuna bo'lmagan bo'lsa, obuna xabarini yuborish
            context.user_data['original_command'] = update
            await send_subscription_message(update, context)
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapped

def unlimited_tokens(func):
    """Adminlar uchun cheksiz tokenlar"""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Agar admin bo'lsa, tokenlar sonini tekshirmasdan o'tkazib yuborish
        if db.is_admin(user_id):
            return await func(update, context, *args, **kwargs)
        
        # Oddiy foydalanuvchilar uchun tokenlar sonini tekshirish
        available_tokens = db.get_user_attribute(user_id, "n_available_tokens")
        
        if available_tokens &lt;= 0:
            await update.message.reply_text(
                "⚠️ Sizda yetarli token yo'q. Iltimos, token sotib oling yoki admindan so'rang."
            )
            return
        
        return await func(update, context, *args, **kwargs)
    
    return wrapped
