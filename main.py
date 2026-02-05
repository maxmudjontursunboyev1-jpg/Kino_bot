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

def run():
    # Agar port 8080 band bo'lsa, boshqa portni sinab ko'rish mumkin
    try:
        app.run(host='0.0.0.0', port=8080)
    except OSError as e:
        logging.error(f"Webserverni ishga tushirishda xatolik: {e}. Port 8080 band bo'lishi mumkin.")
        # Boshqa portni sinab ko'rish yoki xabar berish
        try:
            app.run(host='0.0.0.0', port=5000) # Masalan, 5000 portini sinab ko'ramiz
            logging.info("Webserver 5000 portida ishga tushirildi.")
        except Exception as e_fallback:
            logging.error(f"Qo'shimcha portda ham ishga tushirishda xatolik: {e_fallback}")


def keep_alive():
    t = Thread(target=run)
    t.start()

# --- SOZLAMALAR ---
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID')) if os.getenv('ADMIN_ID') else 0
# Agar MOVIE_CHANNEL environment variable dan olinmasa, default qiymat berish yoki xatolik chiqarish
# Agar sizda kanal ID si bo'lmasa, uni o'rnating yoki environment variable orqali berib keting
MOVIE_CHANNEL = os.getenv('CHANNEL_ID') or -1001234567890 # Misol uchun default qiymat, o'zgartiring yoki env da o'rnating

if not API_TOKEN:
    logging.error("BOT_TOKEN environment variable o'rnatilmagan!")
    exit()
if ADMIN_ID == 0:
    logging.warning("ADMIN_ID environment variable o'rnatilmagan! Admin funksiyalari ishlamaydi.")
if MOVIE_CHANNEL == -1001234567890: # Agar default qiymat bo'lsa
     logging.warning("MOVIE_CHANNEL environment variable o'rnatilmagan yoki noto'g'ri! Kino ko'chirish ishlamaydi.")


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- BAZA ---
DB_NAME = "users.db"
try:
    db = sqlite3.connect(DB_NAME, check_same_thread=False)
    cursor = db.cursor()
    # Foydalanuvchilar jadvali
    cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
    # Sozlamalar jadvali
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    # Majburiy obuna kanallari jadvali
    cursor.execute("CREATE TABLE IF NOT EXISTS channels (id INTEGER PRIMARY KEY AUTOINCREMENT, link TEXT UNIQUE, type TEXT, username TEXT)")

    # Boshlang'ich sozlamalarni qo'shish (agar mavjud bo'lmasa)
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('sub_status', 'on')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_text', 'Kanalga aʼzo boʻling')")
    cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('btn_url', 'https://t.me/your_channel')") # Bu linkni ham o'zgartirish kerak
    db.commit()
except sqlite3.Error as e:
    logging.error(f"Ma'lumotlar bazasiga ulanishda xatolik: {e}")
    exit()

class AdminStates(StatesGroup):
    """Admin buyruqlari uchun FSM holatlari."""
    waiting_for_ad = State() # Reklama yuborish uchun
    waiting_for_btn_text = State() # Tugma matnini o'zgartirish uchun
    waiting_for_btn_url = State() # Tugma linkini o'zgartirish uchun
    waiting_for_channel_link = State() # Majburiy obuna kanali/guruhini qo'shish uchun

# --- TUGMALAR ---

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
            [KeyboardButton(text="⚙️ Sozlamalar")], # Sozlamalar bo'limiga o'tish
            [KeyboardButton(text="📝 Tugma matni"), KeyboardButton(text="🔗 Tugma linki")]
        ], resize_keyboard=True
    )

def settings_kb():
    """Sozlamalar bo'limi tugmalari."""
    sub_button_text = get_sub_status_text()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=sub_button_text)], # Obunani yoqish/o'chirish
            [KeyboardButton(text="➕ Majburiy obuna kanal/guruh")], # Kanal qo'shish/boshqarish
            [KeyboardButton(text="🔄 Qayta ishga tushirish")], # Qayta ishga tushirish
            [KeyboardButton(text="⬅️ Ortga")] # Asosiy panellga qaytish
        ], resize_keyboard=True
    )

# --- FUNKSIYALAR ---

async def check_all_subs(user_id):
    """Foydalanuvchi majburiy obunani bajarganligini tekshiradi."""
    try:
        cursor.execute("SELECT value FROM settings WHERE key='sub_status'")
        status_row = cursor.fetchone()
        if status_row and status_row[0] == 'off':
            return True # Obuna o'chirilgan bo'lsa, hamma kirishi mumkin
    except sqlite3.Error as e:
        logging.error(f"Obuna statusini tekshirishda xatolik: {e}")
        return False # Xatolik yuzaga kelsa, kirishni taqiqlash yaxshi

    # Agar MOVIE_CHANNEL to'g'ri berilgan bo'lsa, uni tekshiramiz
    if MOVIE_CHANNEL and MOVIE_CHANNEL != -1001234567890: # Default qiymat emasligini tekshiramiz
        try:
            member = await bot.get_chat_member(chat_id=MOVIE_CHANNEL, user_id=user_id)
            if member.status in ['member', 'administrator', 'creator']:
                return True
        except Exception as e:
            logging.warning(f"Kanal a'zoligini tekshirishda xatolik ({MOVIE_CHANNEL}, {user_id}): {e}")
            # Agar kanal topilmasa yoki xatolik bo'lsa, kirishni taqiqlash
            pass

    # Agar MOVIE_CHANNEL dan tashqari boshqa kanallar ham bo'lsa, ularni ham tekshirish kerak
    # Bu qismni channels jadvalidan o'qib to'ldirish mumkin
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
                logging.warning(f"Qo'shimcha kanal a'zoligini tekshirishda xatolik ({channel_id}, {user_id}): {e}")
    except sqlite3.Error as e:
        logging.error(f"Majburiy obuna kanallarini olishda xatolik: {e}")

    return False # Agar hech bir shart bajarilmasa, obuna talab qilinadi

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    try:
        # Foydalanuvchi allaqachon mavjud bo'lsa, hech narsa qilmaydi
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        db.commit()
    except sqlite3.Error as e:
        logging.error(f"Foydalanuvchini bazaga qo'shishda xatolik ({user_id}): {e}")

    if user_id == ADMIN_ID:
        await message.answer("🛠 <b>Admin panel</b>", reply_markup=main_admin_kb(), parse_mode="HTML")
    else:
        is_subscribed = await check_all_subs(user_id)
        if not is_subscribed:
            # Obuna bo'lmaganlar uchun tugma bilan xabar
            try:
                cursor.execute("SELECT value FROM settings WHERE key='btn_text'")
                b_text = cursor.fetchone()[0] if cursor.fetchone() else "Kanalga a'zo bo'ling"
                cursor.execute("SELECT value FROM settings WHERE key='btn_url'")
                b_url = cursor.fetchone()[0] if cursor.fetchone() else "https://t.me/error_channel" # Xatolik holati uchun

                ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_text, url=b_url)]])
                await message.answer("❌ Botdan foydalanish uchun kanalga a'zo bo'ling!", reply_markup=ikb)
            except sqlite3.Error as e:
                logging.error(f"Start buyrug'ida tugma ma'lumotlarini olishda xatolik: {e}")
                await message.answer("❌ Botdan foydalanish uchun kanalga a'zo bo'ling! (Sozlamalarda xatolik)")
        else:
            await message.answer("🍿 <b>Xush kelibsiz!</b>\n\nKino kodini yuboring 🎥", parse_mode="HTML")

# --- KINO QIDIRISH (ASOSIY QO'SHIMCHA) ---
@dp.message(F.text.isdigit())
async def search_movie(message: types.Message):
    user_id = message.from_user.id
    if not await check_all_subs(user_id):
        # Obuna bo'lmaganlar uchun tugma bilan xabar
        try:
            cursor.execute("SELECT value FROM settings WHERE key='btn_text'")
            b_text = cursor.fetchone()[0] if cursor.fetchone() else "Kanalga a'zo bo'ling"
            cursor.execute("SELECT value FROM settings WHERE key='btn_url'")
            b_url = cursor.fetchone()[0] if cursor.fetchone() else "https://t.me/error_channel"

            ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_text, url=b_url)]])
            await message.answer("❌ Avval kanalga a'zo bo'ling!", reply_markup=ikb)
        except sqlite3.Error as e:
            logging.error(f"Kino qidirishda tugma ma'lumotlarini olishda xatolik: {e}")
            await message.answer("❌ Avval kanalga a'zo bo'ling! (Sozlamalarda xatolik)")
        return

    # Agar MOVIE_CHANNEL to'g'ri berilgan bo'lsa, kino ko'chirishni sinab ko'ramiz
    if MOVIE_CHANNEL and MOVIE_CHANNEL != -1001234567890:
        try:
            message_id_to_copy = int(message.text)
            # Inline tugmani sozlamalardan olamiz
            cursor.execute("SELECT value FROM settings WHERE key='btn_text'")
            b_text = cursor.fetchone()[0] if cursor.fetchone() else "Kanalga a'zo bo'ling"
            cursor.execute("SELECT value FROM settings WHERE key='btn_url'")
            b_url = cursor.fetchone()[0] if cursor.fetchone() else "https://t.me/error_channel"

            ikb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=b_text, url=b_url)]])

            await bot.copy_message(
                chat_id=message.chat.id,
                from_chat_id=MOVIE_CHANNEL,
                message_id=message_id_to_copy,
                reply_markup=ikb
            )
        except ValueError:
            await message.answer("Iltimos, faqat raqam yuboring.")
        except sqlite3.Error as e:
            logging.error(f"Kino qidirishda tugma ma'lumotlarini olishda xatolik: {e}")
            await message.answer("Tugma sozlamalarini olishda xatolik.")
        except Exception as e:
            logging.error(f"Xabarni ko'chirishda xatolik (Kanal: {MOVIE_CHANNEL}, ID: {message.text}): {e}")
            await message.answer("😔 Bu kod bilan kino topilmadi yoki xatolik yuzaga keldi.")
    else:
        await message.answer("Kino ko'chirish uchun sozlamalar to'liq emas. Admin bilan bog'laning.")


# --- ADMIN PANEL QO'SHIMCHALARI ---

@dp.message(F.text == "📝 Tugma matni", F.from_user.id == ADMIN_ID)
async def set_text(message: types.Message, state: FSMContext):
    await message.answer("Kanalga a'zo bo'lish tugmasi uchun yangi matnni yuboring:")
    await state.set_state(AdminStates.waiting_for_btn_text)

@dp.message(AdminStates.waiting_for_btn_text)
async def save_text(message: types.Message, state: FSMContext):
    new_text = message.text
    try:
        cursor.execute("UPDATE settings SET value=? WHERE key='btn_text'", (new_text,))
        db.commit()
        await message.answer(f"✅ Tugma matni '{new_text}' saqlandi!", reply_markup=main_admin_kb())
    except sqlite3.Error as e:
        logging.error(f"Tugma matnini saqlashda xatolik: {e}")
        await message.answer("❌ Tugma matnini saqlashda xatolik yuzaga keldi.")
    await state.clear()

@dp.message(F.text == "🔗 Tugma linki", F.from_user.id == ADMIN_ID)
async def set_url(message: types.Message, state: FSMContext):
    await message.answer("Kanalga a'zo bo'lish tugmasi uchun yangi linkni yuboring (masalan, https://t.me/your_channel):")
    await state.set_state(AdminStates.waiting_for_btn_url)

@dp.message(AdminStates.waiting_for_btn_url)
async def save_url(message: types.Message, state: FSMContext):
    new_url = message.text.strip()
    # Oddiy URL tekshiruvi
    if not (new_url.startswith('http://') or new_url.startswith('https://')):
        await message.answer("❌ Bu haqiqiy URL manzili emas. Iltimos, to'g'ri URL kiriting (masalan, https://t.me/...).")
        return

    try:
        cursor.execute("UPDATE settings SET value=? WHERE key='btn_url'", (new_url,))
        db.commit()
        await message.answer(f"✅ Tugma linki '{new_url}' saqlandi!", reply_markup=main_admin_kb())
    except sqlite3.Error as e:
        logging.error(f"Tugma linkini saqlashda xatolik: {e}")
        await message.answer("❌ Tugma linkini saqlashda xatolik yuzaga keldi.")
    await state.clear()

# --- SOZLAMALAR BO'LIMI HANDLERLARI ---

@dp.message(F.text == "⚙️ Sozlamalar", F.from_user.id == ADMIN_ID)
async def admin_settings(message: types.Message):
    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>", reply_markup=settings_kb(), parse_mode="HTML")

@dp.message(F.text.contains("Obuna:"), F.from_user.id == ADMIN_ID)
async def toggle_sub(message: types.Message):
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

@dp.message(F.text == "➕ Majburiy obuna kanal/guruh", F.from_user.id == ADMIN_ID)
async def manage_channels_start(message: types.Message, state: FSMContext):
    # Bu yerda mavjud kanallarni ko'rsatish va yangi qo'shish imkonini berish mumkin
    # Hozircha faqat yangi qo'shishni boshlaymiz
    await message.answer("Kanal yoki guruh linkini yuboring (masalan, t.me/joinchat/xxxx yoki @channel_username):")
    await state.set_state(AdminStates.waiting_for_channel_link)

@dp.message(AdminStates.waiting_for_channel_link)
async def save_channel_link(message: types.Message, state: FSMContext):
    link = message.text.strip()
    if not link:
        await message.answer("Link bo'sh bo'lishi mumkin emas.")
        return

    channel_type = 'channel' # Default
    username = None

    if link.startswith('@'):
        username = link
        channel_type = 'username' # Agar @ bilan boshlansa, username deb hisoblaymiz
    elif 't.me/' in link:
        parts = link.split('/')
        username = parts[-1] # Oxirgi qismni username deb olamiz
        if 'joinchat' in link:
            channel_type = 'invite_link'
        else:
            channel_type = 'channel_or_group'
    else:
        await message.answer("Noto'g'ri formatdagi link. Iltimos, t.me/... yoki @username formatida yuboring.")
        return

    try:
        # Agar MOVIE_CHANNEL ni almashtirmoqchi bo'lsangiz, shu yerda o'zgartirish kerak
        # Hozircha faqat channels jadvaliga qo'shamiz
        cursor.execute("INSERT OR IGNORE INTO channels (link, type, username) VALUES (?, ?, ?)", (link, channel_type, username))
        db.commit()
        await message.answer(f"✅ Kanal/guruh '{link}' muvaffaqiyatli qo'shildi!")

        # Agar MOVIE_CHANNEL hali o'rnatilmagan bo'lsa, birinchi qo'shilgan kanalni MOVIE_CHANNEL ga o'rnatsak bo'ladi
        if MOVIE_CHANNEL == -1001234567890: # Agar default qiymat bo'lsa
            # Kanal ID sini olish uchun get_chat ishlatish mumkin, lekin bu murakkabroq va qo'shimcha ruxsat talab qiladi
            # Hozircha linkni o'zi saqlanadi. Agar siz MOVIE_CHANNEL ni avtomatik o'rnatsangiz,
            # uni ham environment variable yoki boshqa usul bilan o'zgartirish kerak bo'ladi.
            logging.info("MOVIE_CHANNEL hali o'rnatilmagan. Yangi qo'shilgan kanalni asosiy kino kanali sifatida ishlatish uchun qo'shimcha sozlash kerak.")

    except sqlite3.Error as e:
        logging.error(f"Kanalni bazaga qo'shishda xatolik: {e}")
        await message.answer(f"❌ Kanalni bazaga qo'shishda xatolik yuzaga keldi.")

    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>", reply_markup=settings_kb(), parse_mode="HTML")
    await state.clear()


@dp.message(F.text == "🔄 Qayta ishga tushirish", F.from_user.id == ADMIN_ID)
async def restart_bot_command(message: types.Message):
    await message.answer("🔄 Bot qayta ishga tushirilyapti...")
    # Bu yerda botni haqiqatdan qayta ishga tushirish mexanizmi bo'lishi kerak.
    # Agar serverda botni boshqarish imkoniyati bo'lsa (systemd, Docker, etc.), shu yerda amalga oshiriladi.
    # Masalan, os.execv(sys.executable, [sys.executable] + sys.argv) kabi kodlar ishlatilishi mumkin,
    # lekin bu server muhitiga bog'liq. Hozircha faqat xabar ko'rinishida qoldiramiz.
    await message.answer("Bot qayta ishga tushirildi (simulyatsiya).")
    await message.answer("⚙️ <b>Sozlamalar bo'limi</b>", reply_markup=settings_kb(), parse_mode="HTML")

@dp.message(F.text == "⬅️ Ortga", F.from_user.id == ADMIN_ID)
async def back_to_main(message: types.Message):
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=main_admin_kb(), parse_mode="HTML")

# --- ASOSIY FUNKSIYA ---
def main():
    keep_alive() # Webserverni ishga tushirish
    logging.info("Bot ishga tushirildi...")
    try:
        asyncio.run(dp.start_polling(bot))
    except KeyboardInterrupt:
        logging.info("Bot to'xtatildi.")
    except Exception as e:
        logging.error(f"Bot ishga tushirishda umumiy xatolik: {e}")

if __name__ == '__main__':
    main()
 
