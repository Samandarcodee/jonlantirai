# 🎬 Google Veo 3.1 Video Bot - Sozlash

## ✅ TO'G'RI VARIANTNI TOPDINGIZ!

Bu **haqiqiy Google Veo 3.1** API bilan ishlaydi! 🚀

---

## 📋 KERAKLI NARSALAR

### 1️⃣ Google Cloud Project

- ✅ Project yaratilgan: `third-tome-478112-k6`
- ✅ API Key olingan: `AIzaSyDBPZUEcfCl5vPiPKl6b9WjzqyTb4ImAcs`

### 2️⃣ Service Account (YANGI KERAK!)

API key yetarli emas - **Service Account** JSON fayli kerak!

---

## 🔧 SOZLASH QADAMLARI

### 1️⃣ Service Account Yarating

Google Cloud Console'da:

1. **☰ Menu** → **IAM & Admin** → **Service Accounts**
2. **+ CREATE SERVICE ACCOUNT** tugmasini bosing
3. Nom kiriting: `telegram-bot-service`
4. **CREATE AND CONTINUE** bosing
5. Role qo'shing: **Vertex AI User** ✅
6. **CONTINUE** → **DONE**

### 2️⃣ Service Account Key Yarating

1. Yaratgan Service Account'ingizni toping
2. **Actions** (3 nuqta) → **Manage keys**
3. **ADD KEY** → **Create new key**
4. **JSON** formatini tanlang ✅
5. **CREATE** bosing

**JSON fayl yuklab olinadi!** 📥

### 3️⃣ JSON Faylni Joylashtiring

Yuklab olingan JSON faylni loyiha papkasiga ko'chiring:

```
AI-NEO/
  ├── bot_google_veo.py
  ├── service-account.json  ← SHU YERGA!
  └── .env
```

Fayl nomini `service-account.json` deb o'zgartiring.

### 4️⃣ Vertex AI API ni Yoqing

Google Cloud Console'da:

1. **☰ Menu** → **APIs & Services** → **Library**
2. Qidiruv: `Vertex AI API`
3. **ENABLE** tugmasini bosing ✅

### 5️⃣ .env Faylini Yarating

```env
# Telegram Bot Token
TELEGRAM_BOT_TOKEN=sizning_telegram_bot_token

# Google Cloud Project ID (skrinshotdan)
GOOGLE_PROJECT_ID=third-tome-478112-k6

# Location (default: us-central1)
GOOGLE_LOCATION=us-central1

# Model ID
GOOGLE_MODEL_ID=veo-3.1-generate-preview

# Service Account JSON fayli (default: service-account.json)
GOOGLE_SERVICE_ACCOUNT_FILE=service-account.json
```

### 6️⃣ Dependencies O'rnating

```bash
pip install -r requirements_veo.txt
```

### 7️⃣ Botni Ishga Tushiring

```bash
python bot_google_veo.py
```

---

## 🎮 QANDAY ISHLAYDI

### Foydalanuvchi:
📸 Rasm yuboradi  
💬 "Quyosh chiqayotgan dengiz bo'yi"

### Bot:
⏳ Qabul qildim...  
⚙️ Video yaratilmoqda (5-10 daqiqa)...  
✅ Video tayyor!  
🎬 [8 soniyalik video]

---

## 📊 VIDEO PARAMETRLARI

### Duration (Davomiyligi):
- 5-8 soniya (8 tavsiya etiladi)

### Aspect Ratio:
- `16:9` - Landscape (YouTube, TV)
- `9:16` - Portrait (TikTok, Reels)
- `1:1` - Square (Instagram)

### Resolution:
- `1080p` - Full HD ✅
- `720p` - HD

### Prompt Enhancement:
- `true` - AI promptni yaxshilaydi ✅

---

## ⚠️ MUHIM ESLATMALAR

### Billing:

Google Veo **PULLI XIZMAT**:
- ~$0.10-0.20 har bir video uchun
- Billing account bo'lishi SHART
- Karta bog'lash kerak

### Preview Model:

`veo-3.1-generate-preview` - Preview rejimi
- Test uchun yaxshi
- Cheklangan kirish
- Kelajakda GA (Generally Available) versiya chiqadi

### Kutish Vaqti:

Video yaratish **5-10 daqiqa** oladi:
- Sabr qiling!
- Bot avtomatik kuzatadi
- Tayyor bo'lgach yuboradi

---

## 🐛 MUAMMOLARNI HAL QILISH

### ❌ "Service account file not found"

**Yechim:**
- `service-account.json` faylini loyiha papkasiga qo'ying
- Fayl nomi to'g'ri ekanligini tekshiring

### ❌ "Permission denied"

**Yechim:**
- Service Account'ga **Vertex AI User** roli berilganini tekshiring
- IAM & Admin → Service Accounts → Edit → Add Role

### ❌ "API not enabled"

**Yechim:**
- Vertex AI API yoqilganini tekshiring
- APIs & Services → Library → Vertex AI API → Enable

### ❌ "Quota exceeded"

**Yechim:**
- Billing account faol ekanligini tekshiring
- Quota limitingizni tekshiring
- Quotas & System Limits sahifasiga o'ting

### ❌ "Invalid project ID"

**Yechim:**
- `.env` da PROJECT_ID to'g'ri yozilganini tekshiring
- Skrinshotda: `third-tome-478112-k6`

---

## 💰 NARXLAR (Taxminiy)

| Xizmat | Narx |
|--------|------|
| Veo 3.1 (8s video) | ~$0.10-0.20 |
| Storage | $0.02/GB |
| API calls | Bepul |

**Oyiga ~$10-50** (100-500 video uchun)

---

## 🎯 KEYINGI QADAMLAR

1. ✅ Service Account yarating
2. ✅ JSON faylni yuklab oling
3. ✅ `service-account.json` ga joylashtiring
4. ✅ Vertex AI API ni yoqing
5. ✅ `.env` faylini to'ldiring
6. ✅ `pip install -r requirements_veo.txt`
7. ✅ `python bot_google_veo.py`
8. ✅ Test qiling!

---

## 💡 AFZALLIKLARI

✅ Haqiqiy Google Veo 3.1  
✅ Eng yuqori sifat  
✅ To'g'ridan-to'g'ri Google'dan  
✅ Professional natijalar  
✅ Kelajakda yangilanishlar  

---

**Omad! Video bot yaratishda muvaffaqiyat! 🚀**

