# 🎬 MovieCode Bot — Kod orqali kinolar

Bu Telegram bot foydalanuvchilarga kino kodlarini yuborish orqali tezkorlik bilan kino va seriallarni topish imkonini beradi. Sodda, tez va samarali!

## 🚀 Ishlash prinsipi
Bot juda sodda ishlaydi:
1. Kanaldan yoki guruhdan kino kodini topasiz (masalan: 567).
2. Kodni botga yuborasiz.
3. Bot sizga o'sha kodga tegishli kinoni fayl yoki video formatida yuboradi.

## ✨ Imkoniyatlar
* ⚡️ Tezkor javob: Hech qanday menyularsiz, faqat kod orqali.
* 📂 Keng baza: Minglab kinolar yagona kod tizimiga birlashtirilgan.
* 🤖 Admin Panel: Yangi kinolarni kod bilan yuklash va tahrirlash imkoniyati.
* 📊 Statistika: Bot foydalanuvchilari sonini kuzatish.

## 🛠 Texnik qism
* Til: Python 3.11.0
* Framework: aiogram (Asinxron)
* Ma'lumotlar bazasi: SQLite (Sodda va tezkor ma'lumot saqlash uchun)



## ⚙️ Sozlamalar (.env)
Botingiz ishlashi uchun quyidagi o'zgaruvchilarni sozlang:
`env
BOT_TOKEN=Sizning_Bot_Tokeningiz
ADMIN_ID=Sizning_ID_Raqamingiz
CHANNEL_ID=[-100123456789, ...]  bot ulangan kanal kodni qidirish uchun 
