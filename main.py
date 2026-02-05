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
def home(): return "Bot is alive!"

def run(): app.run(host='0.0.0.0', port=8080)
def keep_alive():
    t = Thread(target=run)
    t.start()

# --- SOZLAMALAR ---
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else 0
CHANNEL_ID = os.getenv('CHANNEL_ID')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA (Yangi ustunlar bilan) ---
db = sqlite3.connect("users.db", check_same_thread=False)
cursor = db.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT UNIQUE, value TEXT)")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_status', 'on')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_text', 'Kino kanalimiz 🍿')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_url', 'https://t.me/your_channel')")
db.commit()

class AdminStates(StatesGroup):
    waiting_for_ad = State()
    waiting_for_btn_text = State()
    waiting_for_btn_url = State()

# --- TUGMALAR ---
def main_admin_kb():
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    status = cursor.fetchone()[0]
    sub_btn = "🔴 Obuna: O'CHIQ" if status == 'off' else "🟢 Obuna: YOQIQ"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama yuborish")],
            [KeyboardButton(text=sub_btn), KeyboardButton(text="🔗 Tugma sozlamalari")],
            [KeyboardButton(text="🔄 Qayta ishga tushirish")]
        ], resize_keyboard=True
    )

def settings_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Tugma matni"), KeyboardButton(text="🔗 Tugma linki")],
            [KeyboardButton(text="⬅️ Orqaga")]
        ], resize_keyboard=True
    )

# --- FUNKSIYALAR ---
async def check_all_subs(user_id):
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    if cursor.fetchone()[0] == 'off': return True
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return m.status in ['member', 'administrator', 'creator']
    except: return False

# --- KINO QIDIRISH VA TUGMA BILAN YUBORISH ---
@dp.message(F.text.isdigit())
async def search_movie(message: types.Message):
    if not await check_all_subs(message.from_user.id):
        await message.answer("❌ Botdan foydalanish uchun kanalga a'zo bo'ling!")
        return

    # Bazadan tugma sozlamalarini olish
    cursor.execute("SELECT value FROM settings WHERE key='btn_text'")
    b_text = cursor.fetchone()[0]
    cursor.execute("SELECT value FROM settings WHERE key='btn_url'")
    b_url = cursor.fetchone()[0]

    # Inline tugma yaratish
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=b_text, url=b_url)]
    ])

    try:
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=CHANNEL_ID,
            message_id=int(message.text),
            reply_markup=ikb
        )
    except:
        await message.answer("😔 Kino topilmadi yoki bot kanalga a'zo emas.")

# --- ADMIN PANEL HANDLERLARI ---
@dp.message(F.text == "🔗 Tugma sozlamalari", F.from_user.id == ADMIN_ID)
async def btn_settings(message: types.Message):
    await message.answer("Tugma matni yoki linkini o'zgartiring:", reply_markup=settings_kb())

@dp.message(F.text == "📝 Tugma matni", F.from_user.id == ADMIN_ID)
async def set_btn_text(message: types.Message, state: FSMContext):
    await message.answer("Yangi tugma matnini kiriting:")
    await state.set_state(AdminStates.waiting_for_btn_text)

@dp.message(AdminStates.waiting_for_btn_text)
async def save_btn_text(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='btn_text'", (message.text,))
    db.commit()
    await message.answer("✅ Tugma matni saqlandi!", reply_markup=main_admin_kb())
    await state.clear()

@dp.message(F.text == "🔗 Tugma linki", F.from_user.id == ADMIN_ID)
async def set_btn_url(message: types.Message, state: FSMContext):
    await message.answer("Yangi linkni kiriting (masalan: https://t.me/...):")
    await state.set_state(AdminStates.waiting_for_btn_url)

@dp.message(AdminStates.waiting_for_btn_url)
async def save_btn_url(message: types.Message, state: FSMContext):
    if message.text.startswith("http"):
        cursor.execute("UPDATE settings SET value=? WHERE key='btn_url'", (message.text,))
        db.commit()
        await message.answer("✅ Tugma linki saqlandi!", reply_markup=main_admin_kb())
        await state.clear()
    else:
        await message.answer("❌ Xato! Link 'http' bilan boshlanishi kerak.")

@dp.message(F.text == "⬅️ Orqaga", F.from_user.id == ADMIN_ID)
async def back_to_main(message: types.Message):
    await message.answer("Admin panel", reply_markup=main_admin_kb())

# --- QOLGAN STANDART HANDLERLAR ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    db.commit()
    kb = main_admin_kb() if message.from_user.id == ADMIN_ID else None
    await message.answer("🍿 Kino kodini yuboring!", reply_markup=kb)

async def main():
    keep_alive()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
