# 🌟 VIP Foydalanuvchilar - Har 6 Soatda 5 Ta Video

## 📋 VIP Foydalanuvchilar Ro'yxati

| User ID | Limit | Davr |
|---------|-------|------|
| **7506450592** | 5 video | 6 soat |
| **5801250458** | 5 video | 6 soat |

## ✅ Qanday Ishlaydi

### 1️⃣ Birinchi Video
- VIP user rasm yuboradi
- Sistema: "✅ Birinchi video, yangi davr boshlanadi"
- 6 soatlik davr boshlanadi
- Video hisoblagich: **1/5**

### 2️⃣ Ikkinchi, Uchinchi, To'rtinchi, Beshinchi Video
- VIP user davom etadi
- Sistema har safar: "✅ Video #{N}/5 ruxsat berildi"
- Video hisoblagich: **2/5**, **3/5**, **4/5**, **5/5**

### 3️⃣ Oltinchi Video (Limit Yetdi)
- VIP user 6-chi video yaratmoqchi
- Sistema: "❌ Limit yetdi (5/5) - 6 soat kutish kerak"
- Kutish vaqti ko'rsatiladi

### 4️⃣ 6 Soat O'tgach
- Yangi davr avtomatik boshlanadi
- Hisoblagich qaytadan **0** ga qaytadi
- Yana **5 ta** video yaratish mumkin

## 🔍 Debug Loglar

Botni ishga tushirganda, quyidagi loglarni ko'rasiz:

```
⭐ User 7506450592 is VIP - checking limit (5 videos per 6 hours)
⭐ VIP user 7506450592 - new period starting or first video - allowing
⭐ Recording VIP user 7506450592 video creation
⭐ VIP user 7506450592 - NEW PERIOD started, videos: 1/5
```

Har bir video uchun:
```
⭐ User 7506450592 is VIP - checking limit (5 videos per 6 hours)
⭐ VIP user 7506450592 - videos in current period: 1/5
⭐ VIP user 7506450592 - can create video (2/5)
⭐ Recording VIP user 7506450592 video creation
⭐ VIP user 7506450592 - video recorded, videos in period: 2/5
```

## 📊 Statistikada Ko'rinishi

VIP foydalanuvchi `/stats` buyrug'ini yuborganda:

```
📊 STATISTIKA

👤 Foydalanuvchi Ismi
🏅 ⭐ VIP (3/5 video qoldi)

🎬 Videolar: 15
✅ Hozir video yarata olasiz!
```

## 🎯 Interface

### Start Xabari
```
🎬 Jonlantir AI ⭐

⭐ Siz VIP foydalanuvchi!
🎬 Har 6 soatda 5 ta video yaratish
✨ Maxsus huquq!
```

### Menyu
```
🎬 Jonlantir AI ⭐

⭐ Siz VIP: Har 6 soatda 5 ta video yaratish!
```

## 🛠 Texnik Detali

### Database Struktura
Har bir VIP user uchun:
```json
{
  "user_id": 7506450592,
  "username": "example",
  "first_name": "Test",
  "videos_created": 15,
  "last_video_time": 1234567890,
  "vip_period_start": 1234567890,      // ← 6 soatlik davr boshi
  "vip_videos_in_period": 3            // ← Joriy davrda yaratilgan videolar
}
```

### Mantiq
1. **can_create_video()** - Video yaratish mumkinmi?
   - VIP tekshiruvi
   - Davr tekshiruvi
   - Video soni tekshiruvi

2. **record_video_creation()** - Video yaratildi
   - VIP tracking
   - Yangi davr boshlash yoki hisoblagich oshirish

## ✅ Test Qilish

### Test 1: Birinchi Video
```bash
# VIP user rasm yuboradi
# Kutilayotgan: ✅ Video yaratiladi
# Log: "NEW PERIOD started, videos: 1/5"
```

### Test 2: 2-5 Videolar
```bash
# VIP user ketma-ket 4 ta rasm yuboradi
# Kutilayotgan: ✅ Hammasi yaratiladi
# Log: "videos in period: 2/5", "3/5", "4/5", "5/5"
```

### Test 3: 6-chi Video (Bloklanishi Kerak)
```bash
# VIP user 6-chi rasm yuboradi
# Kutilayotgan: ❌ "Kutish vaqti" xabari
# Log: "limit reached (5/5) - wait Xh Ym"
```

### Test 4: 6 Soat Keyin
```bash
# 6 soat kutish (yoki database-da vaqtni o'zgartirish)
# VIP user rasm yuboradi
# Kutilayotgan: ✅ Yangi davr, video yaratiladi
# Log: "NEW PERIOD started, videos: 1/5"
```

## 🎉 Xulosa

VIP funksiyasi to'liq tayyor! Ikkala foydalanuvchi (7506450592 va 5801250458) har 6 soatda 5 tadan video yaratishi mumkin.

Agar muammo bo'lsa, loglarni tekshiring - har bir harakat batafsil loglanadi!
