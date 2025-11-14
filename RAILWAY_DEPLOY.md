# Railway'ga Deploy Qilish Qo'llanmasi

Bu loyhani Railway'ga deploy qilish uchun batafsil qo'llanma.

## 📋 Talablar

- Railway account ([railway.com](https://railway.com/))
- GitHub repository (loyha GitHub'da bo'lishi kerak)
- Telegram Bot Token
- Google Cloud Service Account JSON fayli

## 🚀 Deploy Qadamlar

### 1. GitHub'ga Push Qiling

Loyhani GitHub repository'ga push qiling:

```bash
git add .
git commit -m "Railway deployment ready"
git push origin main
```

### 2. Railway'da Yangi Project Yaratish

1. [Railway.app](https://railway.app/) ga kiring
2. "New Project" tugmasini bosing
3. "Deploy from GitHub repo" ni tanlang
4. GitHub repository'ni tanlang va connect qiling

### 3. Environment Variables Qo'shish

Railway dashboard'da **Variables** bo'limiga o'ting va quyidagi o'zgaruvchilarni qo'shing:

#### Majburiy O'zgaruvchilar:

```
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
GOOGLE_PROJECT_ID=your_google_project_id
GOOGLE_LOCATION=us-central1
```

#### Service Account (2 ta usul bor):

**Usul 1: Environment Variable (Tavsiya etiladi)**

`GOOGLE_SERVICE_ACCOUNT_JSON` o'zgaruvchisiga service-account.json faylining **to'liq JSON kontentini** qo'shing:

```
GOOGLE_SERVICE_ACCOUNT_JSON={"type":"service_account","project_id":"...","private_key":"...",...}
```

**Usul 2: Fayl sifatida**

Agar environment variable ishlamasa, Railway'da fayl yuklash imkoniyati bor. `service-account.json` faylini project root'ga qo'shing.

### 4. Build Settings

Railway avtomatik ravishda quyidagilarni aniqlaydi:
- **Build Command**: `pip install -r requirements_veo.txt`
- **Start Command**: `python bot_google_veo.py` (Procfile'dan o'qiladi)

### 5. Deploy

Railway avtomatik ravishda deploy qiladi. **Deployments** bo'limida progress'ni kuzatishingiz mumkin.

## ⚙️ Settings

### Healthcheck

Railway avtomatik healthcheck qiladi. Agar bot polling rejimida ishlayotgan bo'lsa, healthcheck endpoint qo'shishingiz mumkin (ixtiyoriy).

### Scaling

Railway'da botni scale qilish shart emas, chunki bu long-running process. Lekin agar kerak bo'lsa, **Settings** > **Scaling** dan sozlashingiz mumkin.

## 🔍 Troubleshooting

### Bot ishlamayapti

1. **Logs'ni tekshiring**: Railway dashboard'da **Deployments** > **View Logs**
2. **Environment variables'ni tekshiring**: Barcha o'zgaruvchilar to'g'ri qo'shilganligini tekshiring
3. **Service account'ni tekshiring**: `GOOGLE_SERVICE_ACCOUNT_JSON` to'g'ri JSON formatida bo'lishi kerak

### Service Account Xatoligi

Agar service account bilan bog'lanishda muammo bo'lsa:

1. `GOOGLE_SERVICE_ACCOUNT_JSON` o'zgaruvchisini tekshiring
2. JSON format to'g'ri bo'lishi kerak (bitta qator, escape qilingan)
3. Yoki `service-account.json` faylini repository'ga qo'shing

### Build Xatoligi

Agar build paytida xatolik bo'lsa:

1. `requirements_veo.txt` faylida barcha dependencies borligini tekshiring
2. Python versiyasi to'g'ri bo'lishi kerak (Railway avtomatik aniqlaydi)

## 📝 Eslatmalar

- Bot 24/7 ishlashi uchun Railway'da **always-on** rejimini yoqing
- Free tier'da ba'zi cheklovlar bo'lishi mumkin
- Logs'ni doimiy kuzatib boring
- Service account ma'lumotlarini hech qachon public repository'ga commit qilmang!

## 💰 Narx

Railway'ning free tier'i mavjud, lekin production uchun paid plan tavsiya etiladi.

## ✅ Tekshirish

Deploy qilgandan keyin:

1. Railway logs'da "🚀 **Emotsional Video Bot ishga tushdi!**" xabarini ko'rish kerak
2. Telegram'da botga `/start` buyrug'ini yuborib tekshiring
3. Rasm yuborib video yaratishni sinab ko'ring

---

**Muvaffaqiyatli deploy! 🎉**

