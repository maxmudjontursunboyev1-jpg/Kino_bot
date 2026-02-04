import os
import asyncio
import logging
import sqlite3
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- WEBSERVER ---
app = Flask('')
@app.route('/')
def home(): 
    return "Bot is alive!"

def run(): 
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

# --- SOZLAMALAR ---
# Render yoki Environment variables'dan ma'lumotlarni olish
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else 0
MOVIE_CHANNEL = os.getenv('CHANNEL_ID') 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA ---
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT UNIQUE, value TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS channels (link TEXT UNIQUE, type TEXT, username TEXT)") 
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_status', 'on')")
db.commit()

class AdminStates(StatesGroup):
    waiting_for_new_link = State()
    waiting_for_ad = State()

# --- TUGMALAR (KEYBOARDS) ---

def main_admin_kb():
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    status_row = cursor.fetchone()
    status = status_row[0] if status_row else 'on'
    sub_btn = "🔴 Obuna: O'CHIQ" if status == 'off' else "🟢 Obuna: YOQIQ"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama yuborish")],
            [KeyboardButton(text=sub_btn), KeyboardButton(text="🔄 Qayta ishga tushirish")],
            [KeyboardButton(text="🔐 Majburiy obuna kanal/guruh")]
        ], resize_keyboard=True
    )

# --- FUNKSIYALAR ---

async def check_all_subs(user_id):
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    status_row = cursor.fetchone()
    if status_row and status_row[0] == 'off': 
        return True

    cursor.execute("SELECT username FROM channels")
    rows = cursor.fetchall()
    for (uname,) in rows:
        try:
            m = await bot.get_chat_member(chat_id=uname, user_id=user_id)
            if m.status not in ['member', 'administrator', 'creator']: 
                return False
        except Exception: 
            continue
    return True

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    db.commit()

    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 <b>Admin panel</b>", reply_markup=main_admin_kb(), parse_mode="HTML")
    else:
        is_sub = await check_all_subs(message.from_user.id)
        if not is_sub:
            # Bu yerda show_sub_channels funksiyasini chaqirishingiz yoki xabar yuborishingiz kerak
            await message.answer("❌ Botdan foydalanish uchun kanallarga a'zo bo'ling!")
        else:
            await message.answer(
                "🍿 <b>Xush kelibsiz!</b>\n\nKino kodini yuboring. Kino kodlarini Instagram sahifamizdan topishingiz mumkin 👇🏻\n\n"
                "https://www.instagram.com/kino_movie_t.me?igsh=MWtrd3J5eHdwMmUwbA==", 
                parse_mode="HTML",
                disable_web_page_preview=False
            )

# Obuna holatini o'zgartirish
@dp.message(F.text.startswith("🟢 Obuna:") | F.text.startswith("🔴 Obuna:"), F.from_user.id == ADMIN_ID)
async def toggle_sub(message: types.Message):
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    current = cursor.fetchone()[0]
    new_status = 'off' if current == 'on' else 'on'
    cursor.execute("UPDATE settings SET value=? WHERE key='sub_status'", (new_status,))
    db.commit()
    await message.answer(f"Majburiy obuna holati o'zgartirildi: {new_status}", reply_markup=main_admin_kb())

async def main():
    keep_alive() # Webserverni ishga tushirish
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
