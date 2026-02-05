 
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
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is alive!"

def run_webserver():
    """Flask webserverni ishga tushiradi."""
    port = int(os.environ.get('PORT', 8080))
    try:
        app.run(host='0.0.0.0', port=port)
        logging.info(f"Webserver 0.0.0.0:{port} portida ishga tushirildi.")
    except OSError as e:
        logging.error(f"Webserverni ishga tushirishda xatolik (Port: {port}): {e}")
        if port == 8080:
            try:
                port = 5000
                app.run(host='0.0.0.0', port=port)
                logging.info(f"Webserver 0.0.0.0:{port} portida ishga tushirildi.")
            except Exception as e_fallback:
                logging.error(f"Qo'shimcha portda ({port}) ham ishga tushirishda xatolik: {e_fallback}")

def keep_alive():
    """Webserverni alohida thread da ishga tushiradi."""
    thread = Thread(target=run_webserver)
    thread.daemon = True
    thread.start()

# --- SOZLAMALAR ---
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else None
# CHANNEL_ID muhit o'zgaruvchisi kodda MOVIE_CHANNEL_ID sifatida ishlatiladi
MOVIE_CHANNEL_ID = os.getenv('CHANNEL_ID')

# Muhim sozlamalarni tekshirish
if not API_TOKEN:
    logging.error("BOT_TOKEN environment variable o'rnatilmagan! Bot ishlamaydi.")
    exit()
if ADMIN_ID is None:
    logging.warning("ADMIN_ID environment variable o'rnatilmagan! Admin funksiyalari ishlamaydi.")
if not MOVIE_CHANNEL_ID:
    logging.warning("CHANNEL_ID (MOVIE_CHANNEL_ID) environment variable o'rnatilmagan! Kino ko'chirish funksiyasi ishlamaydi.")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA ---
DB_NAME = "bot_data.db"
try:
    db = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = db.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT UNIQUE, type TEXT, username TEXT)")

    # Default sozlamalarni qo'shish (agar mavjud bo'lmasa)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_status', 'on')") # 'on' - yoqilgan, 'off' - o'chirilgan
    # Inline tugma uchun sozlamalar (muhit o'zgaruvchilari ham ishlatiladi)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_text', 'Kanalga aʼzo boʻling')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_url', 'https://t.me/joinchat/AAAAAE_example')") # Bu linkni almashtiring
    db.commit()
    logging.info(f"Ma'lumotlar bazasi '{DB_NAME}' muvaffaqiyatli ulandi va tekshirildi.")
except sqlite3.Error as e:
    logging.error(f"Ma'lumotlar bazasiga ulanishda yoki jadval yaratishda xatolik: {e}")
    exit()

# --- FSM Holatlari ---
class AdminStates(StatesGroup):
    waiting_for_btn_text = State()
    waiting_for_btn_url = State()
    waiting_for_channel_link = State()
    waiting_for_ad_text = State()

# --- TUGMALAR VA KLAVIATURALAR ---

def get_sub_status_text():
    """Obuna holatini ko'rsatuvchi tugma matnini qaytaradi."""
    try:
        cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
        status_row = cursor.fetchone()
        status = status_row[0] if status_row else 'on'
        return "🔴 Obuna: O'CHIQ" if status == 'off' else "🟢 Obuna: YOQIQ"
    except sqlite3.Error as e:
        logging.error(f"Obuna statusini olishda xatolik: {e}")
        return "Obuna holati: Noma'lum"

def main_admin_kb():
    """Asosiy admin paneli tugmalari."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama yuborish")],
            [KeyboardButton(text="⚙️ Sozlamalar")],
            [KeyboardButton(text="📝 Tugma matni"), KeyboardButton(text="🔗 Tugma linki")]
        ], resize_keyboard=True, one_time_keyboard=True
    )

def settings_kb():
    """Sozlamalar bo'limi tugmalari."""
    sub_button_text = get_sub_status_text()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=sub_button_text)],
            [KeyboardButton(text="➕ Majburiy obuna kanallari")],
            [KeyboardButton(text="🔄 Qayta ishga tushirish")],
            [KeyboardButton(text="⬅️ Ortga")]
        ], resize_keyboard=True, one_time_keyboard=True
    )

def get_inline_button():
    """Inline tugmani sozlamalardan (yoki muhit o'zgaruvchilaridan) olib qaytaradi."""
    try:
        # Bazadan o'qishni sinab ko'rish
        cursor.execute("SELECT value FROM settings WHERE key='btn_text'")
        b_text_row = cursor.fetchone()
        b_text = b_text_row[0] if b_text_row and b_text_row[0] else None

        cursor.execute("SELECT value FROM settings WHERE key='btn_url'")
        b_url_row = cursor.fetchone()
        b_url = b_url_row[0] if b_url_row and b_url_row[0] else None

        # Agar bazadan olinmasa, muhit o'zgaruvchilaridan olamiz
        if not b_text:
            b_text = os.getenv('BTN_TEXT', "Kanalga a'zo bo'ling") # Default qiymat
        if not b_url:
            b_url = os.getenv('BTN_URL', "https://t.me/error_channel") # Default qiymat

        # URL ni tekshirish
        if not (b_url.startswith('http://') or b_url.startswith('https://')):
            b_url = "https://t.me/error_channel" # Noto'g'ri URL bo'lsa default

        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_text, url=b_url)]])

    except sqlite3.Error as e:
        logging.error(f"Inline tugma ma'lumotlarini olishda xatolik (bazadan): {e}")
        # Bazadan olinmasa ham, muhit o'zgaruvchilaridan olishni sinab ko'rish
        try:
            b_text = os.getenv('BTN_TEXT', "Kanalga a'zo bo'ling")
            b_url = os.getenv('BTN_URL', "https://t.me/error_channel")
            if not (b_url.startswith('http://') or b_url.startswith('https://')):
                b_url = "https://t.me/error_channel"
            return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_text, url=b_url)]])
        except Exception as e_env:
            logging.error(f"Inline tugma yaratishda umumiy xatolik (muhit o'zgaruvchilaridan ham): {e_env}")
            return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Xatolik", url="#")]])

    except Exception as e:
        logging.error(f"Inline tugma yaratishda umumiy xatolik: {e}")
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Xatolik", url="#")]])

# --- ASOSIY FUNKSIYALAR ---

async def get_user_status(user_id: int) -> bool:
    """Foydalanuvchi majburiy obunani bajarganligini tekshiradi."""
    try:
        cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
        status_row = cursor.fetchone()
        if status_row and status_row[0] == 'off':
            return True # Obuna o'chirilgan bo'lsa, hamma kirishi mumkin
    except sqlite3.Error as e:
        logging.error(f"Obuna statusini olishda xatolik: {e}")
        return False

    # MOVIE_CHANNEL_ID muhit o'zgaruvchisidan olinadi
    if MOVIE_CHANNEL_ID:
        try:
            member = await bot.get_chat_member(chat_id=MOVIE_CHANNEL_ID, user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                return True
        except Exception as e:
            logging.warning(f"Asosiy kanal ({MOVIE_CHANNEL_ID}) a'zoligini tekshirishda xatolik ({user_id}): {e}")

    # Qo'shimcha majburiy obuna kanallarini tekshirish
    try:
        cursor.execute("SELECT link FROM channels")
        all_channels = cursor.fetchall()
        for channel_link_tuple in all_channels:
            channel_id = channel_link_tuple[0]
            try:
                member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
                if member.status in ['member', 'administrator', 'creator']:
                    return True
            except Exception as e:
                logging.warning(f"Qo'shimcha kanal ({channel_id}) a'zoligini tekshirishda xatolik ({user_id}): {e}")
    except sqlite3.Error as e:
        logging.error(f"Majburiy obuna kanallarini olishda xatolik: {e}")

    return False

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    try:
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        db.commit()
    except sqlite3.Error as e:
        logging.error(f"Foydalanuvchini bazaga qo'shishda xatolik ({user_id}): {e}")

    if user_id == ADMIN_ID:
        await message.answer("🛠 <b>Admin panel</b>", reply_markup=main_admin_kb(), parse_mode="HTML")
    else:
        is_subscribed = await get_user_status(user_id)
        if not is_subscribed:
            ikb = get_inline_button()
            await message.answer("❌ Botdan foydalanish uchun kanalga a'zo bo'ling!", reply_markup=ikb)
        else:
            await message.answer("🍿 <b>Xush kelibsiz!</b>\n\nKino kodini yuboring 🎥", parse_mode="HTML")

# --- KINO QIDIRISH VA KO'CHIRISH ---
@dp.message(F.text.regexp(r'^\d+$')) # Faqat raqamlardan iborat xabarlarni qabul qiladi
async def search_movie(message: types.Message):
    user_id = message.from_user.id
    if not await get_user_status(user_id):
        ikb = get_inline_button()
        await message.answer("❌ Avval kanalga a'zo bo'ling!", reply_markup=ikb)
        return

    try:
        message_id_to_copy = int(message.text)
        ikb = get_inline_button() # Inline tugmani har safar olamiz

        # MOVIE_CHANNEL_ID muhit o'zgaruvchisidan olinadi
        source_chat_id = MOVIE_CHANNEL_ID
        if not source_chat_id:
            await message.answer("Kino ko'chirish uchun sozlamalar to'liq emas. Admin bilan bog'laning.")
            return

        await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=source_chat_id,
            message_id=message_id_to_copy,
            reply_markup=ikb
        )
    except ValueError:
        await message.answer("Iltimos, faqat kino kodini (raqam) yuboring.")
    except Exception as e:
        logging.error(f"Xabarni ko'chirishda xatolik (Kanal: {source_chat_id}, ID: {message.text}): {e}")
        await message.answer("😔 Bu kod bilan kino topilmadi yoki xatolik yuzaga keldi.")

# --- ADMIN BUYRUQLARI VA HANDLERLARI ---

# Tugma matnini o'zgartirish
@dp.message(F.text == "📝 Tugma matni", F.from_user.id == ADMIN_ID)
async def cmd_set_btn_text(message: types.Message, state: FSMContext):
    await message.answer("Kanalga a'zo bo'lish tugmasi uchun yangi matnni yuboring:")
    await state.set_state(AdminStates.waiting_for_btn_text)

@dp.message(AdminStates.waiting_for_btn_text)
async def save_btn_text(message: types.Message, state: FSMContext):
    new_text = message.text
    try:
        cursor.execute("UPDATE settings SET value=? WHERE key='btn_text'", (new_text,))
        db.commit()
        await message.answer(f"✅ Tugma matni '{new_text}' saqlandi!", reply_markup=main_admin_kb())
    except sqlite3.Error as e:
        logging.error(f"Tugma matnini saqlashda xatolik: {e}")
        await message.answer("❌ Tugma matnini saqlashda xatolik yuzaga keldi.")
    await state.clear()

# Tugma linkini o'zgartirish
@dp.message(F.text == "🔗 Tugma linki", F.from_user.id == ADMIN_ID)
async def cmd_set_btn_url(message: types.Message, state: FSMContext):
    await message.answer("Kanalga a'zo bo'lish tugmasi uchun yangi linkni yuboring (masalan, https://www.instagram.com/your_username/):")
    await state.set_state(AdminStates.waiting_for_btn_url)

@dp.message(AdminStates.waiting_for_btn_url)
async def save_btn_url(message: types.Message, state: FSMContext):
    new_url = message.text.strip()
    if not (new_url.startswith('http://') or new_url.startswith('https://')):
        await message.answer("❌ Bu haqiqiy URL manzili emas. Iltimos, to'g'ri URL kiriting (masalan, https://t.me/... yoki https://www.instagram.com/...).")
        return

    try:
        cursor.execute("UPDATE settings SET value=? WHERE key='btn_url'", (new_url,))
        db.commit()
        await message.answer(f"✅ Tugma linki '{new_url}' saqlandi!", reply_markup=main_admin_kb())
    except sqlite3.Error as e:
        logging.error(f"Tugma linkini saqlashda xatolik: {e}")
        await message.answer("❌ Tugma linkini saqlashda xatolik yuzaga keldi.")
    await state.clear()

# Sozlamalar bo'limiga kirish
@dp.message(F.text == "⚙️ Sozlamalar", F.from_user.id == ADMIN_ID)
async def cmd_settings(message: types.Message):
    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>", reply_markup=settings_kb(), parse_mode="HTML")

# Obuna holatini o'zgartirish
@dp.message(F.text.contains("Obuna:"), F.from_user.id == ADMIN_ID)
async def cmd_toggle_sub_status(message: types.Message):
    try:
        cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
        current_status = cursor.fetchone()[0]
        new_status = 'off' if current_status == 'on' else 'on'
        cursor.execute("UPDATE settings SET value=? WHERE key='sub_status'", (new_status,))
        db.commit()
        status_text = "YOQIQ" if new_status == 'off' else "O'CHIQ"
        await message.answer(f"✅ Obuna holati o'zgartirildi. Yangi holat: {status_text}")
        await message.answer("⚙️ <b>Sozlamalar bo'limi</b>", reply_markup=settings_kb(), parse_mode="HTML")
    except sqlite3.Error as e:
        logging.error(f"Obuna holatini o'zgartirishda xatolik: {e}")
        await message.answer("❌ Obuna holatini o'zgartirishda xatolik yuzaga keldi.")

# Majburiy obuna kanallarini boshqarish (qo'shish)
@dp.message(F.text == "➕ Majburiy obuna kanallari", F.from_user.id == ADMIN_ID)
async def cmd_manage_channels(message: types.Message, state: FSMContext):
    await message.answer("Kanal yoki guruh linkini yuboring (masalan, t.me/joinchat/AAAA... yoki @channel_username):")
    await state.set_state(AdminStates.waiting_for_channel_link)

@dp.message(AdminStates.waiting_for_channel_link)
async def save_channel_link(message: types.Message, state: FSMContext):
    link = message.text.strip()
    if not link:
        await message.answer("Link bo'sh bo'lishi mumkin emas.")
        return

    channel_type = 'unknown'
    username = None

    if link.startswith('@'):
        username = link
        channel_type = 'username'
    elif 't.me/' in link:
        parts = link.split('/')
        username = parts[-1]
        if 'joinchat' in link:
            channel_type = 'invite_link'
        else:
            channel_type = 'channel_or_group'
    else:
        await message.answer("Noto'g'ri formatdagi link. Iltimos, t.me/... yoki @channel_username formatida yuboring.")
        return

    try:
        cursor.execute("INSERT OR IGNORE INTO channels (link, type, username) VALUES (?, ?, ?)", (link, channel_type, username))
        db.commit()
        await message.answer(f"✅ Kanal/guruh '{link}' muvaffaqiyatli qo'shildi!")
        # Agar MOVIE_CHANNEL_ID bo'sh bo'lsa va bu birinchi qo'shilgan kanal bo'lsa, uni MOVIE_CHANNEL_ID ga o'rnatsak bo'ladi
        if not MOVIE_CHANNEL_ID:
             logging.warning("MOVIE_CHANNEL_ID muhit o'zgaruvchisi bo'sh. Birinchi qo'shilgan kanalni asosiy qilib olish mumkin.")
             # Agar MOVIE_CHANNEL_ID ni ham bazadan boshqarishni istasangiz, bu yerda qo'shimcha logikani qo'shish kerak.
    except sqlite3.Error as e:
        logging.error(f"Kanalni bazaga qo'shishda xatolik: {e}")
        await message.answer(f"❌ Kanalni bazaga qo'shishda xatolik yuzaga keldi.")

    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>", reply_markup=settings_kb(), parse_mode="HTML")
    await state.clear()

# Qayta ishga tushirish
@dp.message(F.text == "🔄 Qayta ishga tushirish", F.from_user.id == ADMIN_ID)
async def cmd_restart_bot(message: types.Message):
    await message.answer("🔄 Bot qayta ishga tushirilyapti...")
    # Bu yerda botni haqiqatdan qayta ishga tushirish mexanizmi bo'lishi kerak.
    await message.answer("Bot qayta ishga tushirildi (simulyatsiya).")
    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>", reply_markup=settings_kb(), parse_mode="HTML")

# Ortga qaytish
@dp.message(F.text == "⬅️ Ortga", F.from_user.id == ADMIN_ID)
async def cmd_back_to_main(message: types.Message):
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=main_admin_kb(), parse_mode="HTML")

# Reklama yuborish (Admin uchun)
@dp.message(F.text == "📢 Reklama yuborish", F.from_user.id == ADMIN_ID)
async def cmd_send_ad(message: types.Message, state: FSMContext):
    await message.answer("Yuboriladigan reklamani yuboring. U barcha foydalanuvchilarga tarqatiladi.")
    await state.set_state(AdminStates.waiting_for_ad_text)

@dp.message(AdminStates.waiting_for_ad_text)
async def send_ad_to_users(message: types.Message, state: FSMContext):
    ad_text = message.text
    try:
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        success_count = 0
        error_count = 0
        for user_id_tuple in users:
            user_id = user_id_tuple[0]
            try:
                await bot.send_message(chat_id=user_id, text=ad_text)
                success_count += 1
                await asyncio.sleep(0.05) # Telegram limitlarini chetlab o'tish uchun kichik pauza
            except Exception as e:
                logging.warning(f"Reklamani {user_id} ga yuborishda xatolik: {e}")
                error_count += 1
                if "bot was blocked by the user" in str(e): # Agar foydalanuvchi botni bloklagan bo'lsa
                    try:
                        cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                        db.commit()
                        logging.info(f"Foydalanuvchi {user_id} bloklagani sababli o'chirildi.")
                    except sqlite3.Error as db_e:
                        logging.error(f"Bloklagan foydalanuvchini o'chirishda xatolik: {db_e}")

        await message.answer(f"✅ Reklama yuborildi!\n\n"
                           f"Muvaffaqiyatli yuborilganlar: {success_count}\n"
                           f"Xatoliklar: {error_count}")
    except sqlite3.Error as e:
        logging.error(f"Foydalanuvchilarni reklama uchun olishda xatolik: {e}")
        await message.answer("❌ Reklamani yuborishda xatolik yuzaga keldi.")
    await state.clear()
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=main_admin_kb(), parse_mode="HTML")

# --- STATISTIKA FUNKSIYASI ---
@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def cmd_statistics(message: types.Message):
    try:
        # Umumiy foydalanuvchilar soni
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users_row = cursor.fetchone()
        total_users = total_users_row[0] if total_users_row else 0

        # Bugungi qo'shilgan foydalanuvchilar soni (agar joined_at ustuni bo'lsa)
        # Hozircha bu ustun yo'q, shuning uchun bu qismni kommentda qoldiramiz
        # cursor.execute("SELECT COUNT(*) FROM users WHERE joined_at >= date('now', 'start of day')")
        # today_users_row = cursor.fetchone()
        # today_users = today_users_row[0] if today_users_row else 0

        stats_text = f"📊 **Statistika**\n\n" \
                     f"🔹 Umumiy foydalanuvchilar: {total_users}"
                     # f"\n🔹 Bugun qo'shilganlar: {today_users}" # Agar qo'shilsa

        await message.answer(stats_text, parse_mode="HTML", reply_markup=main_admin_kb())

    except sqlite3.Error as e:
        logging.error(f"Statistika ma'lumotlarini olishda xatolik: {e}")
        await message.answer("❌ Statistikani olishda xatolik yuzaga keldi.")
    except Exception as e:
        logging.error(f"Statistika handlerida umumiy xatolik: {e}")
        await message.answer("❌ Noma'lum xatolik yuzaga keldi.")


# --- ASOSIY DASTURNI BOSHLASH ---
def main():
    logging.info("Bot ishga tushirildi...")
    keep_alive() # Webserverni ishga tushirish
    # Aiogram event loopini boshlash
    asyncio.run(dp.start_polling(bot))

if __name__ == '__main__':
    main()
 
