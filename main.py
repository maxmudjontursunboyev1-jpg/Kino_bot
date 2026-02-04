import logging
import sqlite3
from aiogram import Bot, Dispatcher, types, executor
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

# KONFIGURATSIYA
API_TOKEN = '7774202263:AAGjD1rcVLY9aJGIDzF8luHGIMjETxFmrrI'
ADMIN_ID = 7339714216  # BU YERGA TELEGRAM ID-INGIZNI YOZING
CHANNEL_ID = -100123456789  # VIDEOLAR SAQLANADIGAN KANAL ID-SI

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Ma'lumotlar bazasini sozlash
conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS movies 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, file_id TEXT)""")
conn.commit()

class AdminStates(StatesGroup):
    waiting_for_video = State()
    waiting_for_code = State()

# --- ADMIN BUYRUQLARI ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("Kino qo'shish ➕", "Statistika 📊")
        await message.answer("Xush kelibsiz, Admin!", reply_markup=kb)
    else:
        await message.answer("Salom! Kino olish uchun uning kodini yuboring.")

@dp.message_handler(lambda message: message.text == "Kino qo'shish ➕", user_id=ADMIN_ID)
async def add_movie_start(message: types.Message):
    await AdminStates.waiting_for_video.set()
    await message.answer("Videoni yuboring (yoki Forward qiling):")

@dp.message_handler(content_types=['video'], state=AdminStates.waiting_for_video)
async def get_video(message: types.Message, state: FSMContext):
    # Videoni kanalga yuborish
    sent_msg = await message.forward(CHANNEL_ID)
    await state.update_data(file_id=sent_msg.video.file_id)
    await AdminStates.waiting_for_code.set()
    await message.answer("Endi ushbu kino uchun kod kiriting (masalan: 101):")

@dp.message_handler(state=AdminStates.waiting_for_code)
async def get_code(message: types.Message, state: FSMContext):
    data = await state.get_data()
    code = message.text
    
    cursor.execute("INSERT INTO movies (code, file_id) VALUES (?, ?)", (code, data['file_id']))
    conn.commit()
    
    await state.finish()
    await message.answer(f"Muvaffaqiyatli saqlandi! Kod: {code}")

# --- FOYDALANUVCHI QIDIRUVI ---
@dp.message_handler()
async def search_movie(message: types.Message):
    code = message.text
    cursor.execute("SELECT file_id FROM movies WHERE code=?", (code,))
    result = cursor.fetchone()
    
    if result:
        await message.answer_video(result[0], caption=f"Kodni bo'yicha topildi: {code}")
    else:
        if message.from_user.id != ADMIN_ID:
            await message.answer("Bunday kodli kino topilmadi ❌")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
