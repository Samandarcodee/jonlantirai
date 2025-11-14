# 🎬 Telegram Image to Video Bot - Loyiha Ma'lumotlari

## 📦 Yaratilgan Fayllar

### 🔥 Asosiy Fayllar
1. **bot.py** - Asosiy bot kodi (Telegram bot + Veo 3 integratsiyasi)
2. **requirements.txt** - Python dependencies
3. **README.md** - Ingliz tilida qo'llanma
4. **QANDAY_ISHLATISH.md** - O'zbek tilida batafsil qo'llanma
5. **ENV_SETUP.txt** - .env faylini sozlash bo'yicha ko'rsatma

### 🚀 Ishga Tushirish Skriptlari
6. **setup.py** - Avtomatik sozlash skripti
7. **start.bat** - Windows uchun ishga tushirish
8. **start.sh** - Linux/Mac uchun ishga tushirish

### ⚙️ Konfiguratsiya
9. **.gitignore** - Git ignore fayllar ro'yxati
10. **.env** - API kalitlar (SIZ YARATISHINGIZ KERAK!)

---

## 🎯 Botning Imkoniyatlari

### ✅ Qiladi:
- 📸 Foydalanuvchidan rasm qabul qiladi
- 🎬 Rasmni 8 soniyalik videoga aylantiradi
- 🤖 Google Veo 3 AI dan foydalanadi
- 💬 O'zbek tilida javob beradi
- ⏱️ Real-time status yangilanishi
- 🎨 Custom prompt qo'llab-quvvatlaydi

### 🎨 Misol Foydalanish:

**Foydalanuvchi:**
- Rasm yuboradi: [Tog' manzarasi]
- Yozadi: "Quyosh chiqayotgan tog'lar"

**Bot:**
1. ⏳ "Rasmingizni qabul qildim!"
2. ⚙️ "Video yaratilmoqda..."
3. ✅ "Video tayyor!" + [8 soniyalik video]

---

## 🔧 Texnik Ma'lumotlar

### Ishlatilgan Texnologiyalar:
- **Python 3.8+**
- **python-telegram-bot 20.7** - Telegram Bot API
- **requests 2.31.0** - HTTP so'rovlar
- **python-dotenv 1.0.0** - Environment variables
- **Google Veo 3 API** - Video generatsiya

### API Endpoints:
- Create Video: `https://api.cometapi.com/veo/v1/video/create`
- Check Status: `https://api.cometapi.com/veo/v1/video/status/{task_id}`

### Video Parametrlari:
- Model: `veo3-pro`
- Duration: `8 seconds` (o'zgartirish mumkin)
- Aspect Ratio: `16:9` (landscape)
- Format: MP4

---

## 📝 Tez Boshlash (3 qadam)

### 1️⃣ API Kalitlarni Oling

**Telegram Bot:**
- @BotFather → /newbot → Token oling

**Veo 3 API:**
- CometAPI.com → Sign Up → API Key oling

### 2️⃣ .env Faylini Yarating

Loyiha papkasida `.env` nomli fayl yarating:

```env
TELEGRAM_BOT_TOKEN=sizning_telegram_token
VEO3_API_KEY=sizning_veo3_key
```

Batafsil: `ENV_SETUP.txt` faylini o'qing

### 3️⃣ Botni Ishga Tushiring

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
chmod +x start.sh
./start.sh
```

**Yoki qo'lda:**
```bash
pip install -r requirements.txt
python bot.py
```

---

## 🎨 Sozlamalarni O'zgartirish

`bot.py` faylini oching va quyidagilarni toping:

### Video Davomiyligi O'zgartirish:
```python
# 72-qator atrofida
duration="8"  # 5, 10, 15 ga o'zgartiring
```

### Video Nisbatini O'zgartirish:
```python
# 73-qator atrofida
aspect_ratio="16:9"  # "9:16" (vertical), "1:1" (kvadrat)
```

### Kutish Vaqtini O'zgartirish:
```python
# 267-qator atrofida
video_url = veo3_generator.wait_for_video(
    task_id, 
    max_wait_time=300,  # 600 soniyaga oshiring
    check_interval=10   # 15 soniyaga oshiring
)
```

### Tilni O'zgartirish:
Barcha matnlar `bot.py` da. Qidiruv qiling:
- `start()` funksiyasi - start xabari
- `help_command()` funksiyasi - help xabari
- `handle_photo()` funksiyasi - jarayon xabarlari

---

## 🔍 Bot Kodining Tuzilishi

### Asosiy Komponentlar:

```python
1. Veo3VideoGenerator class
   └─ create_video_from_image()  # Video yaratish
   └─ get_video_status()          # Status tekshirish
   └─ wait_for_video()            # Video tayyor bo'lishini kutish

2. Bot Handlers
   └─ start()                     # /start buyrug'i
   └─ help_command()              # /help buyrug'i
   └─ handle_photo()              # Rasm handler
   └─ handle_message()            # Matn handler

3. main()                         # Bot ishga tushiruvchi
```

### Ishlov Berish Oqimi:

```
1. User rasm yuboradi
   ↓
2. Bot rasmni Telegram'dan oladi
   ↓
3. Rasm URL ni Veo 3 API ga yuboradi
   ↓
4. API task_id qaytaradi
   ↓
5. Bot har 10 soniyada status tekshiradi
   ↓
6. Video tayyor bo'lganda URL qaytadi
   ↓
7. Bot videoni foydalanuvchiga yuboradi
```

---

## ❓ Tez-Tez Beriladigan Savollar

### Q: Bot ishlayapti, lekin video kelmayapti?
**A:** 
1. VEO3_API_KEY to'g'ri ekanini tekshiring
2. API limitingiz tugagan bo'lishi mumkin
3. max_wait_time ni oshiring (600 soniya)

### Q: "API javob bermadi" xatosi chiqyapti?
**A:**
1. Internet aloqasini tekshiring
2. CometAPI.com ishlab turibdimi tekshiring
3. API kalitingiz aktiv ekanini tekshiring

### Q: Botga rasm yuborilmayapti?
**A:**
1. Rasmni "Compress" qilmasdan yuboring
2. Rasm hajmi 10MB dan kichik bo'lishi kerak
3. Format: JPEG yoki PNG

### Q: Video sifati pastmi?
**A:**
- Yuqori sifatli rasm ishlating (min 512x512)
- Aniq va batafsil prompt yozing
- `veo3-pro` model ishlatilmoqda (eng yaxshi)

### Q: Botni 24/7 ishlatish?
**A:**
- Heroku, AWS, yoki VPS ishlatish kerak
- Batafsil: `QANDAY_ISHLATISH.md` → "Serverda Ishlatish"

---

## 💡 Pro Maslahatlar

### 🎯 Yaxshi Promptlar:
- ✅ "Quyosh chiqayotgan dengiz bo'yida to'lqinlar harakatlanadi"
- ✅ "Yomg'ir yog'ayotgan shahar ko'chalari, avtomobillar o'tmoqda"
- ❌ "dengiz"
- ❌ "shahar"

### 📸 Yaxshi Rasmlar:
- Yuqori sifat (HD yoki yuqori)
- Aniq va yorug'
- Harakatga boy ob'ektlar bor

### ⚡ Tezlashtirish:
- `check_interval` ni 5 soniyaga tushiring
- Bir vaqtda ko'p video yaratmang
- API limit ostida qoling

---

## 🚀 Keyingi Qadamlar

### O'zgartirish G'oyalari:
1. ✨ Ko'p rasmdan video yaratish
2. 🎵 Video ga musiqa qo'shish
3. 📊 Statistika qo'shish (nechta video yaratilgan)
4. 💾 Database qo'shish (history)
5. 🌐 Web dashboard yaratish
6. 👥 Ko'p foydalanuvchi uchun queue tizimi

### Yangi Funksiyalar:
```python
# Video davomiyligini tanlash
/video 5  # 5 soniyalik
/video 10 # 10 soniyalik

# Nisbatni tanlash
/vertical # 9:16 (TikTok, Reels)
/square   # 1:1 (Instagram)

# History
/history  # Avvalgi videolar
```

---

## 📞 Yordam va Qo'llab-quvvatlash

### Hujjatlar:
- 📖 README.md - Ingliz tilida
- 📖 QANDAY_ISHLATISH.md - O'zbek tilida batafsil
- 📖 ENV_SETUP.txt - .env sozlash

### Muammolar:
- Konsolda xatolarni o'qing
- `python setup.py` ni ishga tushiring
- Loglarni tekshiring

### Aloqa:
- GitHub Issues
- Telegram Support
- Email

---

## 📊 Loyiha Statistikasi

- **Kod qatorlari:** ~400 qator
- **Fayllar soni:** 10 ta
- **Dependencies:** 3 ta paket
- **Qo'llab-quvvatlanadigan tillar:** O'zbek, Ingliz
- **Platform:** Windows, Linux, Mac
- **Python versiyasi:** 3.8+

---

## ⭐ Litsenziya

MIT License - Erkin foydalaning va o'zgartiring!

---

## 🎉 Oxirgi So'z

Ushbu bot Google ning eng zamonaviy **Veo 3** AI modelidan foydalanadi!

Botingiz bilan ajoyib videolar yarating va do'stlaringiz bilan bo'lishing! 🚀

**Omad tilaymiz!** 🎬

