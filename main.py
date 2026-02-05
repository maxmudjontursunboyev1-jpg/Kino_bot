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
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else 0

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA ---
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT UNIQUE, value TEXT)")
cursor.execute("CREATE TABLE IF NOT EXISTS channels (link TEXT UNIQUE, username TEXT)") 
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_status', 'on')")
db.commit()

class AdminStates(StatesGroup):
    waiting_for_ad = State()
    waiting_for_channel = State()

# --- TUGMALAR ---
def main_admin_kb():
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    status = cursor.fetchone()[0]
    sub_btn = "🔴 Obuna: O'CHIQ" if status == 'off' else "🟢 Obuna: YOQIQ"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama yuborish")],
            [KeyboardButton(text=sub_btn), KeyboardButton(text="➕ Kanal qo'shish")],
            [KeyboardButton(text="🔄 Qayta ishga tushirish")]
        ], resize_keyboard=True
    )

# --- FUNKSIYALAR ---
async def check_all_subs(user_id):
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    if cursor.fetchone()[0] == 'off': return True

    cursor.execute("SELECT username FROM channels")
    channels = cursor.fetchall()
    for (uname,) in channels:
        try:
            m = await bot.get_chat_member(chat_id=uname, user_id=user_id)
            if m.status not in ['member', 'administrator', 'creator']: 
                return False
        except Exception: continue
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
            await message.answer("❌ Botdan foydalanish uchun kanallarga a'zo bo'ling!")
        else:
            await message.answer("🍿 Xush kelibsiz! Kino kodini yuboring.")

# Statistika
@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def show_stats(message: types.Message):
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    await message.answer(f"👥 Bot a'zolari soni: {count} ta")

# Obuna holatini o'zgartirish
@dp.message(F.text.contains("Obuna:"), F.from_user.id == ADMIN_ID)
async def toggle_sub(message: types.Message):
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    current = cursor.fetchone()[0]
    new_status = 'off' if current == 'on' else 'on'
    cursor.execute("UPDATE settings SET value=? WHERE key='sub_status'", (new_status,))
    db.commit()
    await message.answer(f"Holat o'zgardi: {new_status}", reply_markup=main_admin_kb())

# Reklama yuborish (FSM bilan)
@dp.message(F.text == "📢 Reklama yuborish", F.from_user.id == ADMIN_ID)
async def start_ad(message: types.Message, state: FSMContext):
    await message.answer("Reklama matnini yoki rasm/videoni yuboring:")
    await state.set_state(AdminStates.waiting_for_ad)

@dp.message(AdminStates.waiting_for_ad, F.from_user.id == ADMIN_ID)
async def send_ad(message: types.Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for (uid,) in users:
        try:
            await message.copy_to(chat_id=uid)
            count += 1
        except: continue
    await message.answer(f"Reklama {count} kishiga yuborildi.")
    await state.clear()

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
