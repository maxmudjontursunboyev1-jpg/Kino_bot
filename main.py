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
# Tugma uchun qo'shimcha sozlamalar
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_text', 'Kanalga a''zo bo''lish')")
cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_url', 'https://t.me/your_channel')")
db.commit()

class AdminStates(StatesGroup):
    waiting_for_new_link = State()
    waiting_for_ad = State()
    waiting_for_btn_text = State() # Yangi
    waiting_for_btn_url = State()  # Yangi

# --- TUGMALAR (ASLIY HOLATDA) ---

def main_admin_kb():
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    status_row = cursor.fetchone()
    status = status_row[0] if status_row else 'on'
    sub_btn = "🔴 Obuna: O'CHIQ" if status == 'off' else "🟢 Obuna: YOQIQ"

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama yuborish")],
            [KeyboardButton(text=sub_btn), KeyboardButton(text="🔄 Qayta ishga tushirish")],
            [KeyboardButton(text="🔐 Majburiy obuna kanal/guruh")],
            [KeyboardButton(text="📝 Tugma matni"), KeyboardButton(text="🔗 Tugma linki")] # Yangi qo'shildi
        ], resize_keyboard=True
    )

# --- FUNKSIYALAR ---

async def check_all_subs(user_id):
    cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
    status_row = cursor.fetchone()
    if status_row and status_row[0] == 'off': 
        return True

    # Environment'dan kelgan asosiy kanalni tekshirish
    try:
        m = await bot.get_chat_member(chat_id=MOVIE_CHANNEL, user_id=user_id)
        if m.status in ['member', 'administrator', 'creator']:
            return True
    except:
        pass
    return False

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
            await message.answer("❌ Botdan foydalanish uchun kanalga a'zo bo'ling!")
        else:
            await message.answer("🍿 <b>Xush kelibsiz!</b>\n\nKino kodini yuboring 🎥", parse_mode="HTML")

# --- KINO QIDIRISH (ASOSIY QO'SHIMCHA) ---
@dp.message(F.text.isdigit())
async def search_movie(message: types.Message):
    if not await check_all_subs(message.from_user.id):
        await message.answer("❌ Avval kanalga a'zo bo'ling!")
        return

    cursor.execute("SELECT value FROM settings WHERE key='btn_text'")
    b_text = cursor.fetchone()[0]
    cursor.execute("SELECT value FROM settings WHERE key='btn_url'")
    b_url = cursor.fetchone()[0]

    ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_text, url=b_url)]])

    try:
        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=MOVIE_CHANNEL,
            message_id=int(message.text),
            reply_markup=ikb
        )
    except:
        await message.answer("😔 Bu kod bilan kino topilmadi.")

# --- ADMIN PANEL QO'SHIMCHALARI ---

@dp.message(F.text == "📝 Tugma matni", F.from_user.id == ADMIN_ID)
async def set_text(message: types.Message, state: FSMContext):
    await message.answer("Tugma matnini yuboring:")
    await state.set_state(AdminStates.waiting_for_btn_text)

@dp.message(AdminStates.waiting_for_btn_text)
async def save_text(message: types.Message, state: FSMContext):
    cursor.execute("UPDATE settings SET value=? WHERE key='btn_text'", (message.text,))
    db.commit()
    await message.answer("✅ Saqlandi!", reply_markup=main_admin_kb())
    await state.clear()

@dp.message(F.text == "🔗 Tugma linki", F.from_user.id == ADMIN_ID)
async def set_url(message: types.
                  
