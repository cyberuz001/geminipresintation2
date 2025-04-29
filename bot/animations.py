import asyncio
import random
from typing import List, Optional

from telegram import Message, Update
from telegram.constants import ParseMode

# Animatsiya turlari
class Animation:
    """Animatsiya uchun asosiy klass"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, **kwargs) -> Message:
        """Animatsiyani ko'rsatish"""
        raise NotImplementedError("Bu metod subklassda amalga oshirilishi kerak")

class LoadingAnimation(Animation):
    """Yuklash animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, duration: int = 3, **kwargs) -> Message:
        """Yuklash animatsiyasini ko'rsatish"""
        loading_symbols = ["⏳", "⌛️"]
        
        for _ in range(duration):
            for symbol in loading_symbols:
                await message.edit_text(f"{symbol} Yuklanmoqda...")
                await asyncio.sleep(0.5)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

class TypingAnimation(Animation):
    """Yozish animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, typing_speed: float = 0.05, **kwargs) -> Message:
        """Yozish animatsiyasini ko'rsatish"""
        current_text = ""
        
        for char in final_text:
            current_text += char
            try:
                await message.edit_text(current_text, parse_mode=ParseMode.HTML)
                # HTML teglar bilan muammolarni oldini olish uchun
                if char in ['<', '>', '&']:
                    await asyncio.sleep(0)
                else:
                    await asyncio.sleep(typing_speed)
            except Exception:
                # Agar xatolik bo'lsa, davom etamiz
                pass
        
        return message

class CountdownAnimation(Animation):
    """Sanoq animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, start: int = 5, **kwargs) -> Message:
        """Sanoq animatsiyasini ko'rsatish"""
        for i in range(start, 0, -1):
            await message.edit_text(f"⏱ {i}...")
            await asyncio.sleep(1)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

class ProgressBarAnimation(Animation):
    """Progress bar animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, steps: int = 10, **kwargs) -> Message:
        """Progress bar animatsiyasini ko'rsatish"""
        for i in range(steps + 1):
            progress = "▓" * i + "░" * (steps - i)
            percentage = i * 100 // steps
            await message.edit_text(f"Yuklanmoqda... {percentage}%\n[{progress}]")
            await asyncio.sleep(0.3)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

class SpinnerAnimation(Animation):
    """Spinner animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, duration: int = 3, **kwargs) -> Message:
        """Spinner animatsiyasini ko'rsatish"""
        spinner_symbols = ["◐", "◓", "◑", "◒"]
        
        for _ in range(duration * 2):
            for symbol in spinner_symbols:
                await message.edit_text(f"{symbol} Yuklanmoqda...")
                await asyncio.sleep(0.25)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

class DotsAnimation(Animation):
    """Nuqtalar animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, duration: int = 3, **kwargs) -> Message:
        """Nuqtalar animatsiyasini ko'rsatish"""
        for _ in range(duration * 3):
            for i in range(1, 4):
                dots = "." * i
                await message.edit_text(f"Yuklanmoqda{dots}")
                await asyncio.sleep(0.3)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

class RocketAnimation(Animation):
    """Raketa animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, **kwargs) -> Message:
        """Raketa animatsiyasini ko'rsatish"""
        frames = [
            "🌑 🌎 🚀       ",
            "🌑 🌎  🚀      ",
            "🌑 🌎   🚀     ",
            "🌑 🌎    🚀    ",
            "🌑 🌎     🚀   ",
            "🌑 🌎      🚀  ",
            "🌑 🌎       🚀 ",
            "🌑 🌎        🚀",
            "🌑 🌎         ✨",
            "🌑 🌎        ✨ ",
            "🌑 🌎       ✨  ",
            "🌑 🌎      ✨   ",
            "🌑 🌎     ✨    ",
            "🌑 🌎    ✨     ",
            "🌑 🌎   ✨      ",
            "🌑 🌎  ✨       ",
            "🌑 🌎 ✨        ",
            "🌑 🌎✨         ",
            "🌑 🌎          "
        ]
        
        for frame in frames:
            await message.edit_text(f"{frame}\nTayyorlanmoqda...")
            await asyncio.sleep(0.2)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

class BrainAnimation(Animation):
    """Miya animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, **kwargs) -> Message:
        """Miya animatsiyasini ko'rsatish"""
        frames = [
            "🧠 O'ylanmoqda",
            "🧠 O'ylanmoqda.",
            "🧠 O'ylanmoqda..",
            "🧠 O'ylanmoqda...",
            "🧠 O'ylanmoqda....",
            "🧠 O'ylanmoqda.....",
            "💭 G'oya paydo bo'ldi!",
            "💡 Topildi!"
        ]
        
        for frame in frames:
            await message.edit_text(frame)
            await asyncio.sleep(0.4)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

class BuildingAnimation(Animation):
    """Qurilish animatsiyasi"""
    
    @staticmethod
    async def animate(message: Message, final_text: str, **kwargs) -> Message:
        """Qurilish animatsiyasini ko'rsatish"""
        frames = [
            "🧱 Qurilmoqda...",
            "🧱🧱 Qurilmoqda...",
            "🧱🧱🧱 Qurilmoqda...",
            "🧱🧱🧱🧱 Qurilmoqda...",
            "🧱🧱🧱🧱🧱 Qurilmoqda...",
            "🧱🧱🧱🧱🧱🧱 Qurilmoqda...",
            "🧱🧱🧱🧱🧱🧱🧱 Qurilmoqda...",
            "🧱🧱🧱🧱🧱🧱🧱🧱 Qurilmoqda...",
            "🏗️ Qurilish davom etmoqda...",
            "🏢 Qurilish yakunlandi!"
        ]
        
        for frame in frames:
            await message.edit_text(frame)
            await asyncio.sleep(0.4)
        
        return await message.edit_text(final_text, parse_mode=ParseMode.HTML)

# Animatsiyalar ro'yxati
ANIMATIONS = [
    LoadingAnimation,
    TypingAnimation,
    CountdownAnimation,
    ProgressBarAnimation,
    SpinnerAnimation,
    DotsAnimation,
    RocketAnimation,
    BrainAnimation,
    BuildingAnimation
]

async def show_random_animation(update: Update, text: str, animation_type: Optional[str] = None) -> Message:
    """Tasodifiy animatsiyani ko'rsatish"""
    message = await update.message.reply_text("⌛")
    
    if animation_type == "loading":
        animation_class = LoadingAnimation
    elif animation_type == "typing":
        animation_class = TypingAnimation
    elif animation_type == "countdown":
        animation_class = CountdownAnimation
    elif animation_type == "progress":
        animation_class = ProgressBarAnimation
    elif animation_type == "spinner":
        animation_class = SpinnerAnimation
    elif animation_type == "dots":
        animation_class = DotsAnimation
    elif animation_type == "rocket":
        animation_class = RocketAnimation
    elif animation_type == "brain":
        animation_class = BrainAnimation
    elif animation_type == "building":
        animation_class = BuildingAnimation
    elif animation_type == "success":
        animation_class = random.choice([RocketAnimation, BrainAnimation])
    elif animation_type == "error":
        animation_class = random.choice([LoadingAnimation, DotsAnimation])
    elif animation_type == "welcome":
        animation_class = random.choice([TypingAnimation, RocketAnimation])
    else:
        animation_class = random.choice(ANIMATIONS)
    
    return await animation_class.animate(message, text)
