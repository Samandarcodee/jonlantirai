# 🚀 Tez Boshlash Qo'llanmasi

## 1️⃣ API Kalitlarni Olish

### Telegram Bot Token

1. Telegram'da [@BotFather](https://t.me/BotFather) ni oching
2. `/newbot` buyrug'ini yuboring
3. Bot uchun nom kiriting (masalan: "Mening Video Botim")
4. Bot uchun username kiriting (masalan: "my_video_bot")
   - Username `bot` bilan tugashi kerak
   - Masalan: `my_video_bot`, `super_video_bot`
5. BotFather sizga **token** beradi:
   ```
   1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```
6. Bu tokenni nusxalab oling ✅

### Veo 3 API Key

**Variant 1: CometAPI (Tavsiya etiladi)**
1. [CometAPI.com](https://www.cometapi.com/) saytiga kiring
2. "Sign Up" tugmasini bosing
3. Email va parol bilan ro'yxatdan o'ting
4. Dashboard ga o'ting
5. "API Keys" bo'limiga o'ting
6. "Create New Key" bosing va Veo 3 uchun kalit yarating
7. API kalitni nusxalab oling ✅

**Variant 2: Google AI Studio**
1. [Google AI Studio](https://makersuite.google.com/) ga kiring
2. Google akkauntingiz bilan kiring
3. API key yarating
4. Veo 3 API ni yoqing

## 2️⃣ Loyihani Sozlash

### Windows

1. **Loyiha papkasini oching**
   ```
   cd C:\Users\Диёрбек\Desktop\AI-NEO
   ```

2. **start.bat faylini ishga tushiring**
   - `start.bat` faylini ikki marta bosing
   - Yoki PowerShell/CMD da:
   ```
   start.bat
   ```

3. **.env faylini to'ldiring**
   - `.env` fayli ochiladi
   - Tokenlarni quyidagicha kiriting:
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   VEO3_API_KEY=sizning_veo3_api_keyingiz
   ```
   - Faylni saqlang (Ctrl+S)

4. **Botni ishga tushiring**
   - `start.bat` ni qayta ishga tushiring
   - Yoki:
   ```
   python bot.py
   ```

### Linux / Mac

1. **Loyiha papkasini oching**
   ```bash
   cd ~/Desktop/AI-NEO
   ```

2. **start.sh ga ruxsat bering**
   ```bash
   chmod +x start.sh
   ```

3. **start.sh ni ishga tushiring**
   ```bash
   ./start.sh
   ```

4. **.env faylini to'ldiring**
   ```bash
   nano .env
   ```
   - Tokenlarni kiriting va Ctrl+X, Y, Enter bilan saqlang

5. **Botni ishga tushiring**
   ```bash
   python bot.py
   ```

## 3️⃣ Botni Test Qilish

1. **Telegram'da botingizni toping**
   - Bot username orqali qidiring (masalan: @my_video_bot)
   
2. **Botni ishga tushiring**
   - `/start` buyrug'ini yuboring
   
3. **Rasm yuboring**
   - Istalgan rasm yuboring
   - Rasm bilan birga tavsif ham yozishingiz mumkin
   
4. **Natijani kuting**
   - Bot 2-5 daqiqa ichida video yaratadi
   - Video tayyor bo'lgach, sizga yuboriladi

## 4️⃣ Maslahatlar

### ✅ Yaxshi natijalar uchun:

- **Sifatli rasmlar** ishlating (kamida 512x512 px)
- **Aniq tavsif** yozing:
  - ✅ "Quyosh chiqayotgan dengiz bo'yida to'lqinlar harakatlanadi"
  - ❌ "dengiz"
  
- **Format:** JPEG, PNG ishlatish tavsiya etiladi
- **Hajm:** 10MB gacha

### 🎬 Video parametrlari:

- Davomiyligi: 8 soniya
- Nisbat: 16:9 (landscape)
- Sifat: HD

### ⚙️ Parametrlarni o'zgartirish:

`bot.py` faylini oching va quyidagilarni o'zgartiring:

```python
# Video davomiyligi (soniyalarda)
duration="8"  # 5 ga o'zgartiring

# Video nisbati
aspect_ratio="16:9"  # "9:16" ga o'zgartiring (vertical)

# Kutish vaqti (soniyalarda)  
max_wait_time=300  # 600 ga o'zgartiring
```

## 5️⃣ Muammolarni Hal Qilish

### ❌ Bot ishlamayapti

**Xato:** `TELEGRAM_BOT_TOKEN not set`
- **Hal:** `.env` faylda token to'g'ri kiritilganini tekshiring
- Token atrofida qo'shtirnoq bo'lmasin
- Bo'sh joy bo'lmasin

**Xato:** `VEO3_API_KEY not set`
- **Hal:** `.env` faylda Veo 3 API key mavjudligini tekshiring

### ❌ Video yaratilmayapti

**Xato:** `API javob bermadi`
- **Hal:** 
  1. Internet aloqasini tekshiring
  2. API kalitingiz aktiv ekanligini tekshiring
  3. API limitingizni tekshiring

**Xato:** `Vaqt tugadi`
- **Hal:** 
  1. `max_wait_time` ni oshiring (masalan, 600)
  2. Internetingizni tekshiring
  3. Qaytadan urinib ko'ring

### ❌ Rasm yuborilmayapti

- Rasm hajmi 10MB dan kichik bo'lishi kerak
- JPEG yoki PNG formatda bo'lishi kerak
- Telegram'da siqilmagan holda yuboring ("File" sifatida emas!)

## 6️⃣ Serverda Ishlatish (24/7)

### Heroku

```bash
# Heroku CLI o'rnating
# https://devcenter.heroku.com/articles/heroku-cli

# Login
heroku login

# Loyiha yarating
heroku create my-video-bot

# Config vars qo'shing
heroku config:set TELEGRAM_BOT_TOKEN=sizning_token
heroku config:set VEO3_API_KEY=sizning_key

# Deploy qiling
git init
git add .
git commit -m "Initial commit"
git push heroku master
```

### VPS (Ubuntu)

```bash
# Serverga kirish
ssh user@your-server-ip

# Loyihani yuklab olish
git clone <repository-url>
cd AI-NEO

# Dependencies o'rnatish
pip3 install -r requirements.txt

# .env sozlash
nano .env

# Botni background da ishga tushirish
nohup python3 bot.py &

# Yoki screen ishlatish
screen -S videobot
python3 bot.py
# Ctrl+A+D bilan exit
```

## 7️⃣ Yordam

Savollar bo'lsa:
- 📧 Email: support@example.com
- 💬 Telegram: @your_support_channel
- 🐛 Issues: GitHub Issues

---

**🎉 Botingiz bilan qiziqarli videolar yarating!**

