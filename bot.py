import os
import time
import logging
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import requests
from dotenv import load_dotenv
import json
import base64
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from PIL import Image
import io
from google.cloud import vision
import google.generativeai as genai

# Load environment variables
load_dotenv()

# Decode service-account.json from base64 environment variable (Railway deployment)
SA_BASE64 = os.getenv('SERVICE_ACCOUNT_JSON_BASE64')
if SA_BASE64:
    try:
        import base64
        sa_json = base64.b64decode(SA_BASE64).decode('utf-8')
        with open('service-account.json', 'w', encoding='utf-8') as f:
            f.write(sa_json)
        print("✅ service-account.json created from base64 environment variable")
    except Exception as e:
        print(f"❌ Error creating service-account.json: {e}")
elif not os.path.exists('service-account.json'):
    print("⚠️  service-account.json not found!")
    print("📝 Set SERVICE_ACCOUNT_JSON_BASE64 environment variable or add service-account.json locally")

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get configuration from environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
GOOGLE_PROJECT_ID = os.getenv('GOOGLE_PROJECT_ID')
GOOGLE_LOCATION = os.getenv('GOOGLE_LOCATION', 'us-central1')
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE', 'service-account.json')
GOOGLE_GEMINI_API_KEY = os.getenv('GOOGLE_GEMINI_API_KEY')

# Configure Google Gemini
if GOOGLE_GEMINI_API_KEY:
    genai.configure(api_key=GOOGLE_GEMINI_API_KEY)
    logger.info("✅ Google Gemini configured")
else:
    logger.warning("⚠️ GOOGLE_GEMINI_API_KEY not set!")

# Admin configuration
ADMIN_IDS = [5928372261]  # Shu ID bilan faqat Admin huquqlari

# Video creation limits (6 hours for regular users)
VIDEO_COOLDOWN_HOURS = 6
VIDEO_COOLDOWN_SECONDS = VIDEO_COOLDOWN_HOURS * 3600

# Database file
USER_DB_FILE = 'users_database.json'

# Loyalty + promotion configuration
LOYALTY_POINT_RULES = {
    'video_creation': 40,
    'text_video': 45,
    'image_generation': 18,
    'image_edit': 15,
}

LOYALTY_LEVELS = [
    {'name': 'Bronze', 'min_points': 0, 'emoji': '🥉', 'benefit': 'Boshlangʻich daraja'},
    {'name': 'Silver', 'min_points': 150, 'emoji': '🥈', 'benefit': '1 ta promo ochiladi'},
    {'name': 'Gold', 'min_points': 350, 'emoji': '🥇', 'benefit': 'VIP promptlar'},
    {'name': 'Platinum', 'min_points': 700, 'emoji': '🏆', 'benefit': 'Tezroq promolar'},
    {'name': 'Diamond', 'min_points': 1200, 'emoji': '💎', 'benefit': 'Cheklovsiz aksiyalar'},
]

LOYALTY_TIER_ORDER = {tier['name']: idx for idx, tier in enumerate(LOYALTY_LEVELS)}

PROMOTION_CATALOG = [
    {
        'id': 'cooldown_skip',
        'name': '⏭️ Cheklovni oʻtkazib yuborish',
        'description': "6 soatlik cheklovni 1 martaga bekor qiladi.",
        'unlock_points': 150,
        'min_tier': 'Silver',
        'cooldown_hours': 72,
        'reward': {'type': 'cooldown_token', 'value': 1}
    },
    {
        'id': 'double_points',
        'name': '✨ 2x Ball Booster',
        'description': "Keyingi video uchun ball ikki baravar bo'ladi (24 soat ichida).",
        'unlock_points': 260,
        'min_tier': 'Gold',
        'cooldown_hours': 120,
        'reward': {'type': 'point_multiplier', 'multiplier': 2.0, 'duration_hours': 24}
    },
    {
        'id': 'vip_prompt_pack',
        'name': '💎 VIP Prompt Pack',
        'description': "Eksklyuziv sahna va nutqlarni ochadi.",
        'unlock_points': 200,
        'min_tier': 'Silver',
        'cooldown_hours': 48,
        'reward': {'type': 'prompt_pack', 'pack_id': 'vip_memories'}
    },
    {
        'id': 'power_speech_pack',
        'name': '🎙️ Motivatsion Nutq Seti',
        'description': "Kuchli nutq va liderlik promptlari.",
        'unlock_points': 420,
        'min_tier': 'Gold',
        'cooldown_hours': 72,
        'reward': {'type': 'prompt_pack', 'pack_id': 'power_speech'}
    }
]

LOYALTY_PROMPT_PACKS = {
    'vip_memories': [
        {
            'name': '💎 VIP Xotiralar',
            'prompt': "CINEMATIC Uzbek heritage portrait IN UZBEK LANGUAGE. Subject looks into camera with teary joyful eyes, whispers heartfelt words about remembering family reunions. Add gentle hand over heart, soft breathing, shimmering bokeh lights. CRITICAL: Uzbek audio delivering 'Oilam mening boyligim... har lahza yodimda' with emotional, premium voice.",
            'uzbek_text': "Oilam mening boyligim... har lahza yodimda."
        },
        {
            'name': '🏮 Premium Yangi Hayot',
            'prompt': "High-end studio lighting, restored vintage Uzbek photo. Character smiles subtly then shares an uplifting Uzbek blessing about hope and new beginnings. Include natural lip sync, micro eye shimmer, premium color grading.",
            'uzbek_text': "Yangi tong bilan umid ham tugʻiladi."
        },
        {
            'name': '🌌 Kino-uslubiy Orzular',
            'prompt': "Epic slow-motion cinematic scene where the subject tells a poetic Uzbek line about chasing dreams. Windswept hair, soft particles, gentle camera push-in, master-grade color science.",
            'uzbek_text': "Orzularimni quvib, osmonga poylayman."
        }
    ],
    'power_speech': [
        {
            'name': '🔥 Liderning Nutqi',
            'prompt': "Photorealistic Uzbek leader delivering motivational speech IN UZBEK LANGUAGE. Strong confident gestures, bold tone, spotlight lighting, subtle camera shake. Audio line: 'Jamoamiz gʻalaba uchun tugʻilgan!'.",
            'uzbek_text': "Jamoamiz gʻalaba uchun tugʻilgan!"
        },
        {
            'name': '⚡ Startap Ruhi',
            'prompt': "Dynamic entrepreneur vibe, subject leans forward, explains vision with excited Uzbek wording about building future tech. Background neon accents, rhythmic breathing, fast cuts.",
            'uzbek_text': "Biz texnologiya bilan kelajakni yasayapmiz!"
        },
        {
            'name': '🛡 Qahramon Kayfiyat',
            'prompt': "Heroic cinematic pose, slow pan, confident expression, Uzbek speech promising to protect loved ones. Include echoing hall ambience and dramatic lighting.",
            'uzbek_text': "Ayrimlar uchun emas, barchamiz uchun himoya qilaman!"
        }
    ]
}


# User Database Manager
class UserDatabase:
    def __init__(self, db_file):
        self.db_file = db_file
        self.data = self.load_db()
    
    def _default_loyalty_state(self):
        next_points = LOYALTY_LEVELS[1]['min_points'] if len(LOYALTY_LEVELS) > 1 else 0
        return {
            'points': 0,
            'tier': LOYALTY_LEVELS[0]['name'],
            'tier_emoji': LOYALTY_LEVELS[0]['emoji'],
            'points_to_next': next_points,
            'last_point_award': 0,
            'streak': {'count': 0, 'best': 0, 'day': None},
            'history': [],
            'promo_claims': {},
            'cooldown_tokens': 0,
            'pending_point_multiplier': 1.0,
            'pending_multiplier_expiry': None,
            'unlocked_prompt_packs': [],
            'bonus_prompts': []
        }
    
    def _ensure_user_schema(self, user_id_str):
        """Ensure base and loyalty fields exist for a user"""
        user = self.data.get(user_id_str)
        if not user or not isinstance(user, dict):
            user = {
                'user_id': int(user_id_str),
                'username': "No_username",
                'first_name': "Noma'lum",
                'videos_created': 0,
                'last_video_time': 0,
                'join_date': time.time(),
                'total_requests': 0
            }
            self.data[user_id_str] = user
        
        if 'loyalty' not in user or not isinstance(user['loyalty'], dict):
            user['loyalty'] = self._default_loyalty_state()
        else:
            defaults = self._default_loyalty_state()
            for key, value in defaults.items():
                if key not in user['loyalty']:
                    if isinstance(value, (dict, list)):
                        user['loyalty'][key] = json.loads(json.dumps(value))
                    else:
                        user['loyalty'][key] = value
        return user
    
    def _update_loyalty_tier(self, loyalty):
        points = loyalty.get('points', 0)
        tier_info = LOYALTY_LEVELS[0]
        for tier in LOYALTY_LEVELS:
            if points >= tier['min_points']:
                tier_info = tier
        loyalty['tier'] = tier_info['name']
        loyalty['tier_emoji'] = tier_info['emoji']
        
        next_points = 0
        for tier in LOYALTY_LEVELS:
            if tier['min_points'] > points:
                next_points = tier['min_points'] - points
                break
        loyalty['points_to_next'] = max(0, next_points)
        return tier_info
    
    def _calculate_streak_bonus(self, loyalty, timestamp):
        current_day = int(timestamp // 86400)
        streak = loyalty.get('streak', {'count': 0, 'best': 0, 'day': None})
        last_day = streak.get('day')
        
        if last_day == current_day:
            # already counted today
            pass
        elif last_day == current_day - 1:
            streak['count'] = streak.get('count', 0) + 1
        else:
            streak['count'] = 1
        
        streak['day'] = current_day
        streak['best'] = max(streak.get('best', 0), streak['count'])
        loyalty['streak'] = streak
        return min(streak['count'] * 2, 20)
    
    def _append_loyalty_history(self, loyalty, entry):
        history = loyalty.get('history', [])
        history.insert(0, entry)
        loyalty['history'] = history[:25]
    
    def load_db(self):
        """Load user database from file"""
        if os.path.exists(self.db_file):
            try:
                with open(self.db_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def save_db(self):
        """Save database to file"""
        try:
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving database: {e}")
    
    def add_user(self, user_id, username, first_name):
        """Add new user to database - Store user ID and username securely"""
        user_id_str = str(user_id)
        if user_id_str not in self.data:
            # Ensure username is not None
            safe_username = username if username else "No_username"
            safe_first_name = first_name if first_name else "Noma'lum"
            
            self.data[user_id_str] = {
                'user_id': user_id,                    # ← INTEGER ID
                'username': safe_username,             # ← USERNAME
                'first_name': safe_first_name,
                'videos_created': 0,
                'last_video_time': 0,
                'join_date': time.time(),
                'total_requests': 0
            }
            self._ensure_user_schema(user_id_str)
            self.save_db()
            logger.info(f"✅ New user added - ID: {user_id}, Username: {safe_username}, Name: {safe_first_name}")
    
    def can_create_video(self, user_id, consume_loyalty_skip=False):
        """Check if user can create video (6 hour cooldown)"""
        # Admin has no limits
        if user_id in ADMIN_IDS:
            return True, 0
        
        user_id_str = str(user_id)
        user = self._ensure_user_schema(user_id_str)
        
        last_time = user.get('last_video_time', 0)
        time_passed = time.time() - last_time
        
        if time_passed >= VIDEO_COOLDOWN_SECONDS:
            return True, 0
        else:
            loyalty = user.get('loyalty', {})
            tokens = loyalty.get('cooldown_tokens', 0)
            if tokens > 0:
                if consume_loyalty_skip:
                    loyalty['cooldown_tokens'] = max(0, tokens - 1)
                    self._append_loyalty_history(loyalty, {
                        'ts': time.time(),
                        'reason': 'cooldown_skip',
                        'points': 0,
                        'tier': loyalty.get('tier', 'Bronze')
                    })
                    self.save_db()
                return True, 0
            time_left = VIDEO_COOLDOWN_SECONDS - time_passed
            return False, time_left
    
    def record_video_creation(self, user_id, reason='video_creation'):
        """Record that user created a video"""
        user_id_str = str(user_id)
        user = self._ensure_user_schema(user_id_str)
        user['last_video_time'] = time.time()
        user['videos_created'] = user.get('videos_created', 0) + 1
        user['total_requests'] = user.get('total_requests', 0) + 1
        points = LOYALTY_POINT_RULES.get(reason, LOYALTY_POINT_RULES['video_creation'])
        return self.add_loyalty_points(user_id, points, reason)
    
    def get_user_stats(self, user_id):
        """Get user statistics"""
        user_id_str = str(user_id)
        if user_id_str in self.data:
            return self._ensure_user_schema(user_id_str)
        return None
    
    def get_all_stats(self):
        """Get overall statistics"""
        total_users = len(self.data)
        total_videos = sum(user.get('videos_created', 0) for user in self.data.values())
        active_today = sum(1 for user in self.data.values() 
                          if time.time() - user.get('last_video_time', 0) < 86400)
        return {
            'total_users': total_users,
            'total_videos': total_videos,
            'active_today': active_today
        }
    
    def add_loyalty_points(self, user_id, base_points, reason):
        """Grant loyalty points and return summary"""
        base_points = max(1, int(base_points or 1))
        user = self._ensure_user_schema(str(user_id))
        loyalty = user['loyalty']
        now_ts = time.time()
        
        # Expire multiplier if needed
        expiry = loyalty.get('pending_multiplier_expiry')
        if expiry and now_ts > expiry:
            loyalty['pending_point_multiplier'] = 1.0
            loyalty['pending_multiplier_expiry'] = None
        
        multiplier = loyalty.get('pending_point_multiplier', 1.0)
        earned = int(base_points * max(1.0, multiplier))
        streak_bonus = self._calculate_streak_bonus(loyalty, now_ts)
        earned_total = max(1, earned + streak_bonus)
        
        loyalty['points'] = loyalty.get('points', 0) + earned_total
        loyalty['last_point_award'] = now_ts
        tier_info = self._update_loyalty_tier(loyalty)
        
        self._append_loyalty_history(loyalty, {
            'ts': now_ts,
            'reason': reason,
            'points': earned_total,
            'tier': tier_info['name']
        })
        
        if multiplier > 1.0:
            loyalty['pending_point_multiplier'] = 1.0
            loyalty['pending_multiplier_expiry'] = None
        
        self.save_db()
        return {
            'points_added': earned_total,
            'total_points': loyalty['points'],
            'tier': loyalty['tier'],
            'tier_emoji': loyalty.get('tier_emoji', ''),
            'points_to_next': loyalty.get('points_to_next', 0),
            'streak': loyalty.get('streak', {}).get('count', 1)
        }
    
    def get_loyalty_profile(self, user_id):
        user = self._ensure_user_schema(str(user_id))
        loyalty = user['loyalty']
        # Refresh tier & multiplier
        self._update_loyalty_tier(loyalty)
        now_ts = time.time()
        expiry = loyalty.get('pending_multiplier_expiry')
        active_multiplier = loyalty.get('pending_point_multiplier', 1.0)
        if expiry and now_ts > expiry:
            loyalty['pending_point_multiplier'] = 1.0
            loyalty['pending_multiplier_expiry'] = None
            active_multiplier = 1.0
            self.save_db()
        
        history = loyalty.get('history', [])[:5]
        
        return {
            'tier': loyalty.get('tier', LOYALTY_LEVELS[0]['name']),
            'tier_emoji': loyalty.get('tier_emoji', LOYALTY_LEVELS[0]['emoji']),
            'points': loyalty.get('points', 0),
            'points_to_next': loyalty.get('points_to_next', 0),
            'cooldown_tokens': loyalty.get('cooldown_tokens', 0),
            'streak': loyalty.get('streak', {}).get('count', 0),
            'best_streak': loyalty.get('streak', {}).get('best', 0),
            'history': history,
            'multiplier': active_multiplier,
            'multiplier_expires': loyalty.get('pending_multiplier_expiry'),
            'available_promotions': len(self.get_available_promotions(user_id)),
            'prompt_packs': loyalty.get('unlocked_prompt_packs', [])
        }
    
    def get_available_promotions(self, user_id):
        user = self._ensure_user_schema(str(user_id))
        loyalty = user['loyalty']
        available = []
        now_ts = time.time()
        tier_name = loyalty.get('tier', LOYALTY_LEVELS[0]['name'])
        tier_order = LOYALTY_TIER_ORDER.get(tier_name, 0)
        
        for promo in PROMOTION_CATALOG:
            if loyalty.get('points', 0) < promo['unlock_points']:
                continue
            if LOYALTY_TIER_ORDER.get(promo['min_tier'], 0) > tier_order:
                continue
            claims = loyalty.get('promo_claims', {}).get(promo['id'], {})
            last_claim = claims.get('last_claim')
            if last_claim and now_ts - last_claim < promo['cooldown_hours'] * 3600:
                continue
            available.append(promo)
        
        return available
    
    def _apply_promo_reward(self, loyalty, promo, now_ts):
        reward = promo.get('reward', {})
        summary = ""
        if reward.get('type') == 'cooldown_token':
            value = reward.get('value', 1)
            loyalty['cooldown_tokens'] = loyalty.get('cooldown_tokens', 0) + value
            summary = f"+{value} ta cooldown token"
        elif reward.get('type') == 'point_multiplier':
            multiplier = reward.get('multiplier', 1.5)
            duration = reward.get('duration_hours', 24) * 3600
            loyalty['pending_point_multiplier'] = multiplier
            loyalty['pending_multiplier_expiry'] = now_ts + duration
            summary = f"{multiplier}x ball {int(duration/3600)} soat"
        elif reward.get('type') == 'prompt_pack':
            pack_id = reward.get('pack_id')
            if pack_id:
                packs = loyalty.get('unlocked_prompt_packs', [])
                if pack_id not in packs:
                    packs.append(pack_id)
                    loyalty['unlocked_prompt_packs'] = packs
                summary = f"{promo['name']} ochildi"
        return summary
    
    def claim_promotion(self, user_id, promo_id):
        user = self._ensure_user_schema(str(user_id))
        loyalty = user['loyalty']
        promo = next((p for p in PROMOTION_CATALOG if p['id'] == promo_id), None)
        if not promo:
            return False, "Promo topilmadi."
        
        tier_name = loyalty.get('tier', LOYALTY_LEVELS[0]['name'])
        if loyalty.get('points', 0) < promo['unlock_points']:
            return False, "Ballar yetarli emas."
        if LOYALTY_TIER_ORDER.get(tier_name, 0) < LOYALTY_TIER_ORDER.get(promo['min_tier'], 0):
            return False, f"{promo['min_tier']} darajasidan keyin ochiladi."
        
        claims = loyalty.setdefault('promo_claims', {}).setdefault(promo_id, {'last_claim': 0, 'times_claimed': 0})
        now_ts = time.time()
        if claims['last_claim'] and now_ts - claims['last_claim'] < promo['cooldown_hours'] * 3600:
            remaining = promo['cooldown_hours'] - int((now_ts - claims['last_claim']) // 3600)
            return False, f"Promo {max(1, remaining)} soatdan keyin yana ochiladi."
        
        reward_summary = self._apply_promo_reward(loyalty, promo, now_ts)
        claims['last_claim'] = now_ts
        claims['times_claimed'] += 1
        self.save_db()
        return True, {
            'promo': promo,
            'reward_summary': reward_summary,
            'loyalty': loyalty
        }
    
    def get_loyalty_prompts(self, user_id):
        user = self._ensure_user_schema(str(user_id))
        loyalty = user['loyalty']
        prompts = []
        for pack_id in loyalty.get('unlocked_prompt_packs', []):
            prompts.extend(LOYALTY_PROMPT_PACKS.get(pack_id, []))
        prompts.extend(loyalty.get('bonus_prompts', []))
        return prompts


# Initialize database
user_db = UserDatabase(USER_DB_FILE)


# Rasmni tahlil qilish va mos prompt yaratish uchun yordamchi funksiya
class ImageAnalyzer:
    def __init__(self, service_account_file):
        self.service_account_file = service_account_file
        
    def analyze_image(self, image_bytes):
        """Rasmni CHUQUR tahlil qilish - odamlar, sifat, rang, holat"""
        try:
            # Vision API client
            credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file
            )
            client = vision.ImageAnnotatorClient(credentials=credentials)
            
            image = vision.Image(content=image_bytes)
            
            # 1. Face detection (yuzlar)
            faces = client.face_detection(image=image).face_annotations
            
            # 2. Label detection (ob'ektlar, vaziyat)
            labels = client.label_detection(image=image).label_annotations
            
            # 3. Image properties (ranglar, sifat)
            props = client.image_properties(image=image).image_properties_annotation
            
            # 4. Safe search (rasm turi)
            safe = client.safe_search_detection(image=image).safe_search_annotation
            
            # 5. Text detection (matn bormi?)
            texts = client.text_detection(image=image).text_annotations
            
            # Ranglarni tahlil qilish
            dominant_colors = []
            if props and props.dominant_colors:
                for color in props.dominant_colors.colors[:5]:  # Ko'proq rang tahlili
                    rgb = color.color
                    dominant_colors.append({
                        'r': rgb.red,
                        'g': rgb.green,
                        'b': rgb.blue,
                        'score': color.score,
                        'pixel_fraction': color.pixel_fraction
                    })
            
            # KENGAYTIRILGAN TAHLIL: Rasm holati va sifati
            is_old_photo = False
            is_low_quality = False
            is_black_white = False
            is_sepia = False
            is_faded = False
            brightness_level = 'normal'
            
            # PIL bilan rasmni ochish va qo'shimcha tahlil
            img_pil = Image.open(io.BytesIO(image_bytes))
            img_width, img_height = img_pil.size
            total_pixels = img_width * img_height
            
            # Sifat aniqlash (o'lcham va piksel bo'yicha)
            if img_width < 400 or img_height < 400:
                is_low_quality = True
            elif total_pixels < 300000:  # 300k pikseldan kam
                is_low_quality = True
            
            # Ranglarni tekshirish
            if dominant_colors:
                # Kulrang/qora-oq aniqlash
                color_variance = []
                for c in dominant_colors[:3]:
                    variance = abs(c['r'] - c['g']) + abs(c['g'] - c['b']) + abs(c['r'] - c['b'])
                    color_variance.append(variance)
                
                avg_variance = sum(color_variance) / len(color_variance)
                
                # Juda kam rang farqi = qora-oq/kulrang
                if avg_variance < 30:
                    is_black_white = True
                    is_old_photo = True
                elif avg_variance < 50:
                    is_faded = True  # Xira rang
                
                # Sepia rang aniqlash (jigarrang ohang)
                if dominant_colors[0]['r'] > 150 and dominant_colors[0]['g'] > 100 and dominant_colors[0]['b'] < 100:
                    if dominant_colors[0]['r'] > dominant_colors[0]['g'] > dominant_colors[0]['b']:
                        is_sepia = True
                        is_old_photo = True
                
                # Yorug'lik darajasi
                avg_brightness = sum([c['r'] + c['g'] + c['b'] for c in dominant_colors[:3]]) / (len(dominant_colors[:3]) * 3)
                if avg_brightness < 80:
                    brightness_level = 'dark'
                elif avg_brightness > 200:
                    brightness_level = 'bright'
            
            analysis = {
                'face_count': len(faces),
                'faces': [],
                'labels': [label.description.lower() for label in labels[:20]],
                'is_old_photo': is_old_photo,
                'is_low_quality': is_low_quality,
                'is_black_white': is_black_white,
                'is_sepia': is_sepia,
                'is_faded': is_faded,
                'brightness_level': brightness_level,
                'dominant_colors': dominant_colors,
                'image_size': (img_width, img_height),
                'has_text': len(texts) > 0,
                'resolution_quality': 'high' if total_pixels > 1000000 else 'medium' if total_pixels > 500000 else 'low'
            }
            
            # Har bir yuzni tahlil qilish
            for face in faces:
                face_info = {
                    'joy': face.joy_likelihood.name,
                    'sorrow': face.sorrow_likelihood.name,
                    'anger': face.anger_likelihood.name,
                    'surprise': face.surprise_likelihood.name,
                    'headwear': face.headwear_likelihood.name,
                    'blurred': face.blurred_likelihood.name,
                    'under_exposed': face.under_exposed_likelihood.name
                }
                analysis['faces'].append(face_info)
            
            logger.info(f"📊 CHUQUR TAHLIL: {analysis['face_count']} yuz | Eski: {is_old_photo} | Qora-oq: {is_black_white} | Sepia: {is_sepia}")
            logger.info(f"📊 Sifat: {analysis['resolution_quality']} | Yorug'lik: {brightness_level} | O'lcham: {img_width}x{img_height}")
            logger.info(f"📊 Labellar: {analysis['labels'][:5]}")
            
            return analysis
            
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            return None
    
    def enhance_old_photo(self, image_bytes, analysis):
        """Eski/xira rasmni zamonaviy, rangli, sifatli qilish - HOLAT ASOSIDA"""
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            import io
            
            # Rasmni ochish
            img = Image.open(io.BytesIO(image_bytes))
            
            # Agar grayscale bo'lsa, RGB ga o'tkazish
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # HOLATGA QARAB YAXSHILASH
            
            # 1. QORA-OQ RASM
            if analysis.get('is_black_white'):
                logger.info("🎨 Qora-oq rasm - ranglantirish rejimi")
                # Rangni sekinroq oshirish (eski rasm uchun tabiiy)
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(1.3)  # 1.3x rangli (past qiymat eski rasm uchun)
                
                # Kontrastni yuqori qilish
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.8)  # 1.8x kontrast
            
            # 2. SEPIA RASM (jigarrang)
            elif analysis.get('is_sepia'):
                logger.info("🎨 Sepia rasm - zamonaviylash rejimi")
                # Rangni ko'proq oshirish
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(2.0)  # 2x rangli
                
                # Kontrast
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.6)
            
            # 3. XIRA RASM
            elif analysis.get('is_faded'):
                logger.info("🎨 Xira rasm - yangilash rejimi")
                # Rang to'yinganligi
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(1.8)
                
                # Kontrast
                enhancer = ImageEnhance.Contrast(img)
                img = enhancer.enhance(1.5)
            
            # 4. PAST SIFATLI RASM
            if analysis.get('is_low_quality'):
                logger.info("🎨 Past sifat - keskinlik rejimi")
                # Keskinlik ko'proq
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(2.5)  # 2.5x keskin
                
                # Shovqinni kamaytirish
                img = img.filter(ImageFilter.SMOOTH_MORE)
            else:
                # Oddiy keskinlik
                enhancer = ImageEnhance.Sharpness(img)
                img = enhancer.enhance(2.0)
                
                img = img.filter(ImageFilter.SMOOTH)
            
            # 5. YORUG'LIK MUVOZANATI
            brightness_level = analysis.get('brightness_level', 'normal')
            if brightness_level == 'dark':
                logger.info("🎨 Qorong'i rasm - yorug'lashtirish")
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(1.4)  # 1.4x yorug'roq
            elif brightness_level == 'bright':
                logger.info("🎨 Juda yorug' rasm - pasaytirish")
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(0.9)  # 0.9x qorong'iroq
            else:
                # Normal yorug'lik
                enhancer = ImageEnhance.Brightness(img)
                img = enhancer.enhance(1.1)
            
            # 6. RAZMERNI YAXSHILASH (agar juda kichik bo'lsa)
            if analysis.get('resolution_quality') == 'low':
                logger.info("🎨 Kichik rasm - kattalashtirish")
                width, height = img.size
                # 2x kattalashtirish
                new_size = (width * 2, height * 2)
                img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Yangi rasmni bytes ga aylantirish
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=95)
            enhanced_bytes = output.getvalue()
            
            logger.info("✨ Rasm yaxshilandi: HOLAT ASOSIDA rangli, sifatli, zamonaviy!")
            return enhanced_bytes
            
        except Exception as e:
            logger.error(f"Photo enhancement error: {e}")
            return image_bytes  # Xatolik bo'lsa asl rasmni qaytarish
    
    def generate_uzbek_prompt(self, analysis):
        """Rasmga mos DINAMIK o'zbek tilidagi prompt va so'zlarni yaratish - HOLAT ASOSIDA"""
        if not analysis:
            return self.get_default_prompt(analysis)
        
        face_count = analysis['face_count']
        faces = analysis['faces']
        labels = analysis['labels']
        
        # RASM HOLATI TAHLILI
        is_old_photo = analysis.get('is_old_photo', False)
        is_black_white = analysis.get('is_black_white', False)
        is_sepia = analysis.get('is_sepia', False)
        is_faded = analysis.get('is_faded', False)
        is_low_quality = analysis.get('is_low_quality', False)
        resolution_quality = analysis.get('resolution_quality', 'medium')
        brightness_level = analysis.get('brightness_level', 'normal')
        
        # PROMPT QOSHIMCHALARI - HOLATGA QARAB
        quality_prefix = ""
        restoration_notes = ""
        
        if is_black_white or is_sepia:
            quality_prefix = "RESTORED vintage photograph brought to modern life, "
            restoration_notes = " Enhanced from vintage black-and-white/sepia photo to vibrant modern quality. Show natural aging character while maintaining photorealistic modern restoration. Preserve authentic vintage feel with improved clarity."
        elif is_faded:
            quality_prefix = "RESTORED faded photograph revitalized, "
            restoration_notes = " Enhanced from faded vintage image to clear modern quality. Restore color vibrancy while maintaining authentic character."
        elif is_low_quality or resolution_quality == 'low':
            quality_prefix = "ENHANCED low-resolution image upscaled to HD, "
            restoration_notes = " Upscaled and enhanced to high definition quality with improved clarity and detail."
        else:
            quality_prefix = "PREMIUM quality photograph, "
            restoration_notes = " High definition photorealistic rendering with professional cinematography."
        
        # Yorug'lik qo'shimchasi
        lighting_note = ""
        if brightness_level == 'dark':
            lighting_note = " Apply balanced professional lighting to illuminate features naturally without losing shadow depth."
        elif brightness_level == 'bright':
            lighting_note = " Balance overly bright areas with professional lighting, maintaining natural highlight-shadow ratio."
        else:
            lighting_note = " Maintain natural balanced lighting with professional cinema-quality setup."
        
        # KENGAYTIRILGAN TAHLIL
        # Yosh toifalari
        is_elderly = any(label in ['senior', 'elderly', 'old', 'grandfather', 'grandmother', 'mature', 'wrinkle'] for label in labels)
        is_middle_aged = any(label in ['adult', 'middle-aged', 'mature adult'] for label in labels)
        is_young = any(label in ['child', 'baby', 'kid', 'youth', 'young', 'teenager', 'toddler'] for label in labels)
        
        # Jins
        is_woman = any(label in ['woman', 'female', 'lady', 'girl', 'mother', 'wife'] for label in labels)
        is_man = any(label in ['man', 'male', 'gentleman', 'boy', 'father', 'husband'] for label in labels)
        
        # Hissiyotlar (kengaytirilgan)
        is_happy = any(face.get('joy') in ['VERY_LIKELY', 'LIKELY'] for face in faces)
        is_sad = any(face.get('sorrow') in ['VERY_LIKELY', 'LIKELY'] for face in faces)
        is_surprised = any(face.get('surprise') in ['VERY_LIKELY', 'LIKELY'] for face in faces)
        
        # Vaziyat va muhit (KENGAYTIRILGAN)
        is_outdoor = any(label in ['outdoor', 'nature', 'sky', 'grass', 'tree', 'mountain', 'park', 'garden'] for label in labels)
        is_wedding = any(label in ['wedding', 'bride', 'groom', 'ceremony', 'celebration'] for label in labels)
        is_religious = any(label in ['prayer', 'mosque', 'religious', 'spiritual', 'praying'] for label in labels)
        has_headwear = any(face.get('headwear') in ['VERY_LIKELY', 'LIKELY'] for face in faces)
        
        # QOSHIMCHA VAZIYATLAR
        is_birthday = any(label in ['birthday', 'cake', 'candle', 'party', 'balloon'] for label in labels)
        is_graduation = any(label in ['graduation', 'diploma', 'academic', 'student'] for label in labels)
        is_professional = any(label in ['office', 'business', 'professional', 'suit', 'tie', 'workplace'] for label in labels)
        is_medical = any(label in ['doctor', 'nurse', 'hospital', 'medical', 'health'] for label in labels)
        is_teacher = any(label in ['teacher', 'classroom', 'school', 'education', 'blackboard'] for label in labels)
        is_military = any(label in ['military', 'soldier', 'uniform', 'army'] for label in labels)
        is_sports = any(label in ['sport', 'football', 'athlete', 'exercise', 'fitness'] for label in labels)
        is_cooking = any(label in ['cooking', 'kitchen', 'food', 'chef', 'restaurant'] for label in labels)
        is_reading = any(label in ['book', 'reading', 'library', 'studying'] for label in labels)
        is_music = any(label in ['music', 'instrument', 'singing', 'guitar', 'piano'] for label in labels)
        is_traveling = any(label in ['travel', 'tourist', 'vacation', 'luggage', 'airport'] for label in labels)
        
        # DINAMIK PROMPT YARATISH (ko'proq vaziyatlar)
        if face_count == 0:
            return self.get_default_prompt(analysis)
        
        # ===== MAXSUS VAZIYATLAR (KENGAYTIRILGAN) =====
        
        # To'y va bayramlar
        elif is_wedding:
            phrases = [
                'Bizning to\'yimizga xush kelibsiz! Baxt-saodatga yo\'ldosh bo\'ling!',
                'Yangi hayotingiz muborak bo\'lsin! Baxtli bo\'ling, sevib yashang!',
                'Qutlug\' bo\'lsin! Oq yo\'l, omad va baraka tilaymiz!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '💒 To\'y Marosimi',
                'prompt': f"PHOTOREALISTIC Uzbek wedding scene IN UZBEK LANGUAGE. Bride and groom in traditional Uzbek dress, genuine joyful expressions, natural lighting. Show authentic celebration: warm smiles, slight head movements, natural eye contact. High-quality skin textures, realistic fabric details on traditional clothes. Smooth, natural body language. CRITICAL: Generate Uzbek audio with traditional celebratory tone. Let them speak: '{phrase}' Use warm, emotional voice with natural Uzbek accent. Add subtle ambient wedding sounds. Cinematic quality, 4K details, natural colors, professional lighting setup.",
                'uzbek_text': phrase
            }
        
        elif is_birthday:
            phrases = [
                'Tug\'ilgan kuningiz muborak! Sog\'-salomat, baxtli bo\'ling!',
                'Ko\'p yil yashang! Omadlaringiz bilan keling!',
                'Hayotingiz gullab-yashnаsin! Baxtli yillar tilaymiz!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '🎂 Tug\'ilgan Kun',
                'prompt': f"Uzbek birthday celebration IN UZBEK LANGUAGE. Show happy birthday person, smiling, celebrating. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use joyful birthday Uzbek tone.",
                'uzbek_text': phrase
            }
        
        # Din va ma'naviyat
        elif is_religious or has_headwear:
            phrases = [
                'Ollohim, bizlarni yaxshi yo\'lda yurgizgin. Oilamizga rahmat-baraka ber',
                'Ilohim, rizq-ruzqimizni kengaytir. Sog\'-salomatlik ber. Amin',
                'Alloh taologa shukr. Bizni doim xayrli ishlarda yurgizgin'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '🤲 Duo va Ibodat',
                'prompt': f"Uzbek person in prayer IN UZBEK LANGUAGE. Spiritual expression, hands raised, peaceful face. IMPORTANT: Uzbek audio. Let them say: '{phrase}. Amin!' Use respectful, spiritual Uzbek tone.",
                'uzbek_text': phrase
            }
        
        # Bitirish va ta'lim
        elif is_graduation:
            phrases = [
                'Tabriklaymiz! Muvaffaqiyatlar tilaymiz! Kelajagingiz yorug\' bo\'lsin!',
                'Diplomingiz muborak! Endi yangi marra boshlandi!',
                'Bitirdingiz! Omadingiz katta bo\'lsin, buyuk ishlar qiling!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '🎓 Bitirish Marosimi',
                'prompt': f"Uzbek graduation celebration IN UZBEK LANGUAGE. Show proud graduate, diploma, happy smile. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use proud, encouraging Uzbek tone.",
                'uzbek_text': phrase
            }
        
        # Professional va ish
        elif is_professional:
            phrases = [
                'Ishlarimiz omadli bo\'lsin! Muvaffaqiyatlarga erishamiz!',
                'Kelajak porloq! Professional bo\'lib ishlaymiz!',
                'Mehnat - eng katta boylik. Halol ish qilamiz!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '💼 Professional',
                'prompt': f"Uzbek professional at work IN UZBEK LANGUAGE. Show confident, determined expression, professional attitude. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use confident professional Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Tibbiyot
        elif is_medical:
            phrases = [
                'Sog\'ligingiz asosiy boylik. O\'zingizni ehtiyot qiling!',
                'Shifobaxsh bo\'ling! Bemorlarni davolash - ulug\' ish!',
                'Salomatlik - eng katta ne\'mat. Sog\'-salomat bo\'ling!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '⚕️ Shifokor',
                'prompt': f"Uzbek medical professional IN UZBEK LANGUAGE. Show caring, professional medical worker. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use caring medical professional Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # O'qituvchi
        elif is_teacher:
            phrases = [
                'Bilim - kuch! O\'qing, o\'rganing, rivoj laning!',
                'O\'quvchilarim, yaxshi o\'qing! Bilimli bo\'ling!',
                'Ta\'lim olish - eng muhim. Har kun yangi narsa o\'rganіng!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '👨‍🏫 Ustoz',
                'prompt': f"Uzbek teacher IN UZBEK LANGUAGE. Show wise, encouraging teacher expression. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use encouraging teacher's Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Harbiy
        elif is_military:
            phrases = [
                'Vatanni himoya qilish - sharaf! Kuchli bo\'ling!',
                'Harbiy xizmat - faxr! Vatan oldida burchimiz!',
                'O\'zbеkiston! Vatanimiz tinch bo\'lsin!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '🎖️ Harbiy',
                'prompt': f"Uzbek military person IN UZBEK LANGUAGE. Show strong, patriotic soldier. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use strong, patriotic Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Sport
        elif is_sports:
            phrases = [
                'Sport - salomatlik! Har kun mashq qiling!',
                'Kuchli bo\'ling! G\'alaba bizniki!',
                'Sportchi bo\'lish - faxr! Maqsadga intilamiz!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '⚽ Sportchi',
                'prompt': f"Uzbek athlete IN UZBEK LANGUAGE. Show energetic, strong athlete. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use energetic athlete's Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Oshpazlik
        elif is_cooking:
            phrases = [
                'Mazali ovqat tayyorlaymiz! Yoqimli ishtaha!',
                'Oshxona san\'ati! Mazali bo\'lsin!',
                'O\'zbek oshxonasi - eng mazali! Ishtaha ochiq!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '👨‍🍳 Oshpaz',
                'prompt': f"Uzbek chef cooking IN UZBEK LANGUAGE. Show happy chef, cooking traditional food. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use friendly chef's Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Kitob o'qish
        elif is_reading:
            phrases = [
                'Kitob o\'qish - eng foydali mashg\'ulot! Bilimli bo\'ling!',
                'Har kun o\'qing! Kitob - eng yaxshi do\'st!',
                'O\'qish orqali rivojlanamiz! Dono bo\'ling!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '📚 Kitobxon',
                'prompt': f"Uzbek person reading book IN UZBEK LANGUAGE. Show thoughtful reader. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use thoughtful reader's Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Musiqa
        elif is_music:
            phrases = [
                'Musiqa - jon ozuqasi! Kuy chaling, qo\'shiq ayting!',
                'San\'at - hayot! Musiqada yashang!',
                'O\'zbek musiqasi - eng go\'zal! Kuylang!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '🎵 Musiqachi',
                'prompt': f"Uzbek musician IN UZBEK LANGUAGE. Show talented musician playing. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use artistic musician's Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Sayohat
        elif is_traveling:
            phrases = [
                'Sayohat qilamiz! Dunyo go\'zal, ko\'ring!',
                'Yangi joylar, yangi tajribalar! Sayohat - hayot!',
                'Sayr qiling! Dunyo katta, ko\'rishga arziydi!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '✈️ Sayohatchi',
                'prompt': f"Uzbek traveler IN UZBEK LANGUAGE. Show excited traveler. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use excited traveler's Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # Tabiat
        elif is_outdoor:
            phrases = [
                'Tabiat go\'zal! Havo toza, ruh tinch!',
                'Tog\'lar, daryolar - Ollohning ne\'mati! Tabiатni asrang!',
                'Ochiq havoda dam oling! Sog\'ligingizga foydali!'
            ]
            phrase = random.choice(phrases)
            return {
                'name': '🌳 Tabiatda',
                'prompt': f"Uzbek person in nature IN UZBEK LANGUAGE. Show peaceful outdoor scene. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use calm nature-loving Uzbek voice.",
                'uzbek_text': phrase
            }
        
        # BITTA ODAM
        elif face_count == 1:
            # Katta yoshlilar
            if is_elderly and is_man:
                # HAR XIL MAVZULAR: Hikmatlar, Xotiralar, Hazillar, Duolar, Hayot Tajribasi
                
                # HISSIYOTGA QARAB ANIQLASH
                if is_happy:
                    # Quvnoq bobo - Kulgi, hazil, qiziqarli xotiralar
                    uzbek_phrases = [
                        'Ha-ha! Yosh paytlarimni esladim! O\'sha kunlar qiziq edi!',
                        'Kulib yashang, bolalar! Kulgi - eng yaxshi dori!',
                        'Esimda, bir marta... voy, qanday qiziq voqea bo\'lgan edi!',
                        'Siz ham mening yoshimda bo\'lgansiz, shunday hazillashardik!',
                        'Hayotdan zavqlaning! Men ham yoshligimda shunday quvnoq edim!'
                    ]
                elif is_sad:
                    # G'amgin bobo - Sog'inish, xotiralar, sabr
                    uzbek_phrases = [
                        'Sizlarni juda sog\'indim... Qachon uchrasharmiz?',
                        'O\'tgan kunlarni eslayman... Qanday go\'zal vaqtlar edi...',
                        'Yolg\'izlikda o\'tirib, sizlarni o\'ylayman...',
                        'Vaqt o\'tib ketdi... Lekin xotiralar abadiy qoladi...',
                        'Sabr qiling, bolalar. Har qanday og\'irlik ham o\'tadi...'
                    ]
                else:
                    # Oddiy bobo - Hikmatlar, maslahatlar, hayot tajribasi
                    uzbek_phrases = [
                        'Men 80 yil yashdim. Shuni bilamanki - oila eng muhim',
                        'Yoshligimda men ham sizlardek edim. Endi tajriba to\'pladim',
                        'Hayotda eng muhimi - halollik. Hech narsadan qo\'rqmang',
                        'Bilasizmi, men yoshligimda qanday qiyin vaqtlarni boshdan kechirganman?',
                        'Ota-onangizni hurmat qiling. Ular siz uchun juda ko\'p qilganlar',
                        'Mehnatingiz bеkarга ketmaydi. Sabr qiling, natija bo\'ladi',
                        'Do\'stlaringizni yaxshi tanlaing. Do\'st - ikkinchi oila',
                        'Vaqtni behuda o\'tkazmang. Har kun - yangi imkoniyat'
                    ]
                
                # EMOTSIYAGA MOS PROMPT VARIANTLARI
                if is_happy:
                    # Quvnoq bobo - kuladi, ko'z qisadi, qo'l silkiydi
                    prompt_styles = [
                        f"HYPER-REALISTIC elderly Uzbek grandfather LAUGHING and smiling joyfully IN UZBEK LANGUAGE. Aged face with deep laugh lines, eyes crinkling with genuine happiness, wide warm smile showing joy. EMOTIONAL: Cheerful chuckling, hearty laughter, nostalgic joy remembering good times. Natural movements: head thrown back slightly in laughter, hand slapping knee, wiping happy tears from eyes, shoulders shaking with mirth. Warm bright lighting capturing joyful mood. CRITICAL: Perfect Uzbek lip-sync with laughter sounds. Authentic elderly voice full of joy and laughter, warm chuckling between words. He speaks happily: '{{phrase}}'. Audio with genuine laughter, joy in voice. Photorealistic: laugh wrinkles deepening, eyes nearly closed from smiling, genuine elderly happiness. Cinematic joyful portrait, bright warm colors, 4K.",
                        
                        f"PHOTOREALISTIC happy Uzbek bobo reminiscing joyfully IN UZBEK LANGUAGE. Elderly face beaming with happiness, eyes twinkling with memories, broad authentic smile. EMOTIONAL: Nostalgic joy, fond memories, cheerful storytelling mood. Natural happy movements: animated hand gestures telling story, nodding enthusiastically, occasional chuckle and eye sparkle. Bright natural lighting showing happy expression. CRITICAL: Uzbek speech with laughter and joy. Elderly voice full of warmth and humor, occasional chuckle mid-sentence. He speaks cheerfully: '{{phrase}}'. High-quality audio capturing happiness and laughter. Ultra-realistic happy wrinkles, smiling eyes, genuine joy expression. Cinema-quality happy portrait, vibrant colors, 4K."
                    ]
                elif is_sad:
                    # G'amgin bobo - sog'inadi, ko'zi yoshlanadi, ohista qaradi
                    prompt_styles = [
                        f"HYPER-REALISTIC elderly Uzbek grandfather showing longing and missing someone IN UZBEK LANGUAGE. Aged face with melancholic expression, eyes glistening with tears or moisture, sad gentle gaze looking distant. EMOTIONAL: Deep longing, nostalgia, missing loved ones, gentle sadness. Natural sorrowful movements: slow sigh, eyes looking down then up wistfully, hand on heart, wiping corner of eye, gentle head shake of sadness. Soft dim lighting creating melancholic mood. CRITICAL: Perfect Uzbek lip-sync with emotional tremor. Elderly voice filled with longing, slight break in voice from emotion, tender sad tone. He speaks with emotion: '{{phrase}}'. Audio with soft sighs, emotional depth, hint of tears. Photorealistic: moisture in eyes, trembling lips, authentic elderly sadness. Cinematic melancholic portrait, muted colors, 4K.",
                        
                        f"PHOTOREALISTIC sad Uzbek bobo missing family IN UZBEK LANGUAGE. Elderly face showing deep emotion, watery eyes, lips slightly trembling, longing gaze. EMOTIONAL: Missing loved ones, nostalgia for past, gentle sorrow mixed with love. Natural sad movements: slow deep breath, eyes closing briefly holding back tears, looking off in distance remembering, hand reaching out as if to touch someone. Soft window light creating contemplative mood. CRITICAL: Uzbek speech with emotional voice breaks. Elderly voice thick with emotion, pauses filled with feeling, tender longing tone. He speaks emotionally: '{{phrase}}'. Audio capturing sadness, gentle sobs or sighs, emotional authenticity. Ultra-realistic: tear ducts glistening, sad smile, genuine elderly emotion. Cinema-grade emotional portrait, cool tones, 4K."
                    ]
                else:
                    # Oddiy bobo - hikmatlar, hayot tajribasi
                    prompt_styles = [
                        f"HYPER-REALISTIC elderly Uzbek grandfather speaking wisdom IN UZBEK LANGUAGE. Authentic aged face with natural wrinkles, weathered skin textures, kind wise eyes. Deep wisdom visible in gentle gaze. Natural subtle movements: slow head nod, slight eye squint when speaking, gentle hand gesture. Realistic lighting showing age lines, natural shadows. Warm, golden hour lighting. CRITICAL: Perfect Uzbek lip-sync. Generate authentic elderly Uzbek male voice, calm and wise tone, slight tremor natural to age. Let him speak clearly: '{{phrase}}'. High-quality audio with room ambiance. Photorealistic details: age spots, grey hair texture, natural facial expressions. Cinematic portrait quality, 4K resolution, professional depth of field.",
                        
                        f"PHOTOREALISTIC Uzbek elder grandfather IN UZBEK LANGUAGE. Deeply weathered face showing lifetime of experience, authentic age spots and wrinkles mapping wisdom. Eyes reflecting decades of knowledge, gentle yet firm gaze. Slow deliberate movements: measured head nod, thoughtful pause, wisdom hand gesture pointing upward. Natural indoor lighting from window, soft shadows emphasizing character lines. CRITICAL: Flawless Uzbek pronunciation and lip-sync. Authentic elderly voice with natural age tremor, authoritative yet loving grandfather tone. Clear speech: '{{phrase}}'. Professional audio capturing voice depth and warmth. Ultra-realistic skin mapping, individual grey hairs visible, micro-expressions of life experience. Cinema-grade portrait, warm color palette, bokeh background, 4K detail."
                    ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '👴 Bobo Hikmat',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            elif is_elderly and is_woman:
                # HAR XIL MAVZULAR: Duolar, Xotiralar, Kulgi, Sog'inish
                
                # HISSIYOTGA QARAB
                if is_happy:
                    # Quvnoq buvi - kuladi, o'ynaydi, xotiralar
                    uzbek_phrases = [
                        'Ha-ha! Nabiralarim! Qanday kattalar bo\'libsizlar!',
                        'Kulib yashang, farzandlarim! Hayot go\'zal!',
                        'Esimda, men yoshligimda ham shunday quvnoq edim!',
                        'Voy-voy! Sizlarni ko\'rib qanday xursandman!',
                        'Ollohga shukr, sizlar sog\'-salomatsiz! Quvonchim cheksiz!'
                    ]
                elif is_sad:
                    # G'amgin buvi - sog'inish, duo, yig'lash
                    uzbek_phrases = [
                        'Farzandlarim... juda sog\'indim sizlarni... Qachon kelasiz?',
                        'Yolg\'izman... Ko\'zimdan yosh ketyapti... Sog\'inganim katta',
                        'Nabiralarim, buvingiz sizlarni kutib yotyapti... Keling...',
                        'Ollohim, yana bir bor ko\'rishga nasib et... Juda sog\'indim...',
                        'Yuragim og\'riyapti... Sizlarsiz yashash qiyin...'
                    ]
                else:
                    # Oddiy buvi - duolar, nasihatlar, mehr
                    uzbek_phrases = [
                        'Farzandlarim, Olloh sizlarni asrasin. Doim yaxshilikda bo\'linglar',
                        'Bolalarim, ona duosi hech qachon bo\'sh ketmaydi. Yaxshi bo\'ing',
                        'Men 70 yil yashdim. Bilaman - mehr eng katta kuch',
                        'Nabiralarim, buvingiz doim siz uchun duo qiladi',
                        'Ollohim, farzandlarimga sog\'-salomat ber. Umrlariga baraka qil',
                        'Bolalarim, oilangizni asrang. Oila - Ollohning ne\'mati',
                        'Katta-kichikni hurmat qiling. Ezgulik qilsangiz, Olloh rozi bo\'ladi',
                        'Sabr-toqatli bo\'ling. Olloh sabrlilarga sevib yordam beradi'
                    ]
                
                # EMOTSIYAGA MOS PROMPT
                if is_happy:
                    # Quvnoq buvi - kuladi, qo'l silkiydi
                    prompt_styles = [
                        f"HYPER-REALISTIC elderly Uzbek grandmother SMILING joyfully with grandchildren IN UZBEK LANGUAGE. Aged female face beaming with happiness, deep smile wrinkles, eyes sparkling with joy seeing grandchildren. EMOTIONAL: Pure grandmotherly joy, overwhelming happiness, loving delight. Natural happy movements: reaching arms forward for hug, clapping hands in joy, wiping happy tears, head nodding enthusiastically. Bright warm lighting showing joyful expression. Traditional ro'mol (headscarf) moving naturally. CRITICAL: Perfect Uzbek lip-sync with joyful tone. Authentic elderly female voice full of happiness and love, slight tremble of joy. She speaks happily: '{{phrase}}'. Audio with laughter, warm joyful tone. Photorealistic: joyful wrinkles deepening, loving eyes, genuine grandmother happiness. Cinematic joyful portrait, bright colors, 4K.",
                        
                        f"PHOTOREALISTIC happy Uzbek buvi laughing with love IN UZBEK LANGUAGE. Elderly grandmother face showing pure joy, warm laugh lines, twinkling loving eyes. EMOTIONAL: Overwhelming love for family, joyful reunion, heart full of happiness. Natural joyful movements: gentle laugh, hand on chest in joy, reaching out lovingly, nodding with delight. Soft natural lighting highlighting happy aged features. CRITICAL: Uzbek speech filled with laughter and joy. Tender elderly female voice, warm chuckles, loving grandmother tone. She speaks joyfully: '{{phrase}}'. High-quality audio with warmth and laughter. Ultra-realistic: happy aged skin, genuine smile, loving expression. Cinema-quality, warm tones, 4K."
                    ]
                elif is_sad:
                    # G'amgin buvi - yig'laydi, sog'inadi
                    prompt_styles = [
                        f"HYPER-REALISTIC elderly Uzbek grandmother CRYING and missing loved ones IN UZBEK LANGUAGE. Aged face with tears rolling down wrinkled cheeks, eyes red and glistening with moisture, lips trembling with emotion. EMOTIONAL: Deep longing for family, overwhelming sadness, missing grandchildren desperately. Natural sorrowful movements: wiping tears with shawl corner, hand over heart in pain, slow sighs, eyes closing to hold back sobs. Soft dim lighting showing emotional vulnerability. CRITICAL: Perfect Uzbek lip-sync with crying sounds. Elderly female voice breaking with emotion, sobs between words, tender heartbroken tone. She speaks through tears: '{{phrase}}'. Audio with crying, voice cracks, emotional depth. Photorealistic: real tears on cheeks, trembling chin, authentic elderly grief. Cinematic emotional portrait, muted sad colors, 4K.",
                        
                        f"PHOTOREALISTIC sad Uzbek buvi longing for family IN UZBEK LANGUAGE. Grandmother face showing deep sorrow, watery eyes looking distant with longing, sad gentle expression. EMOTIONAL: Missing grandchildren, nostalgia for togetherness, gentle crying. Natural sad movements: slow tears falling, dabbing eyes with cloth, looking at old photos gesture, deep sorrowful sighs. Soft window light creating melancholic atmosphere. CRITICAL: Uzbek speech interrupted by emotion. Elderly voice thick with tears, pauses for composure, heartbreaking grandmother tone. She speaks emotionally: '{{phrase}}'. Audio with soft crying, emotional tremor. Ultra-realistic: tear tracks on aged skin, sad loving eyes, genuine elderly longing. Cinema-grade emotional portrait, cool melancholic tones, 4K."
                    ]
                else:
                    # Oddiy buvi - duolar, nasihatlar
                    prompt_styles = [
                        f"PHOTOREALISTIC elderly Uzbek grandmother speaking with love IN UZBEK LANGUAGE. Authentic aged female face, soft wrinkles showing life's wisdom, warm loving eyes. Traditional headscarf (ro'mol) if present, natural fabric textures. Maternal warmth visible in gentle expression. Natural movements: soft smile, slight head tilt, gentle hand reaching forward in blessing gesture. Soft, diffused lighting highlighting kind features. CRITICAL: Perfect lip-sync for Uzbek speech. Generate authentic elderly Uzbek female voice, tender and blessing tone, maternal warmth. Let her speak: '{{phrase}}'. Crystal clear audio with soft room echo. Photorealistic skin details, natural age lines, genuine emotional expression. Professional portrait cinematography, warm color grading, 4K quality.",
                        
                        f"HYPER-REALISTIC Uzbek buvi giving blessings IN UZBEK LANGUAGE. Aged grandmother face with gentle loving expression, prayer-like reverence in eyes, soft wise smile. EMOTIONAL: Blessing grandchildren, maternal protection, spiritual love. Natural blessing movements: hands raised in prayer gesture, gentle head bow, touching heart then extending hand, soft benediction gestures. Warm natural lighting creating spiritual atmosphere. CRITICAL: Flawless Uzbek pronunciation. Elderly female voice full of blessing and love, prayer-like reverence, grandmother's tender tone. She speaks with blessing: '{{phrase}}'. High-quality spiritual audio. Ultra-realistic: aged hands in prayer, loving grandmother eyes, genuine blessing expression. Cinema-quality, warm spiritual tones, 4K."
                    ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '👵 Buvi Nasihati',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            # Yosh odamlar
            elif is_young:
                uzbek_phrases = [
                    'Assalomu alaykum! Men katta bo\'lib olsam, hammaga yordam beraman!',
                    'Salom! Hammangizni juda yaxshi ko\'raman!',
                    'Xayr! Qalaysizlar? Men juda xursandman!',
                    'Men yaxshi bola! O\'qiyman, o\'rganaman!',
                    'Salom! Onam, otam, buvim, bobomni juda yaxshi ko\'raman!',
                    'Men katta bo\'lsam, doctor bo\'laman! Yoki muhandis!',
                    'Assalomu alaykum! Men do\'stlarimni yaxshi ko\'raman!'
                ]
                phrase = random.choice(uzbek_phrases)
                return {
                    'name': '👦 Bola Tabassum',
                    'prompt': f"Young Uzbek child speaking sweetly IN UZBEK LANGUAGE. Show innocent smile, bright eyes, cute expression. IMPORTANT: Uzbek audio. Let them say: '{phrase}'. Use sweet child's Uzbek voice.",
                    'uzbek_text': phrase
                }
            
            # O'rta yoshdagi ayollar
            elif is_woman and is_happy:
                # Quvnoq ona - kuladi, o'ynaydi, faxrlanadi
                uzbek_phrases = [
                    'Bolalarim! Ko\'rib qanday xursandman! Keling quchoqlashaylik!',
                    'Farzandlarim, sizlar mening faxrim! Juda mamnunman!',
                    'Ha-ha! Bolalarim qanday kattalashib ketibdi! Ajoyib!',
                    'Sog\'-salomat ekanмiz! Ollohga ming shukr! Xursandman!',
                    'Mening go\'zal farzandlarim! Sizlardan juda mamnunman!'
                ]
                
                prompt_styles = [
                    f"PHOTOREALISTIC Uzbek mother BEAMING with joy and pride IN UZBEK LANGUAGE. Beautiful mid-age maternal face radiating happiness, eyes sparkling with pride and love, wide genuine smile. EMOTIONAL: Maternal pride, overwhelming love, joyful reunion with children. Natural happy movements: arms opening for embrace, laughing warmly, hand on cheek in delight, nodding with pride. Bright natural lighting showing joyful mother. CRITICAL: Perfect Uzbek lip-sync with joyful maternal voice. Authentic middle-aged female voice full of love and happiness, warm laughter between words. She speaks joyfully: '{{phrase}}'. Audio with maternal warmth and joy. Photorealistic: happy maternal features, genuine loving smile, natural mid-age beauty. Professional portrait, warm vibrant tones, 4K.",
                    
                    f"HYPER-REALISTIC happy Uzbek ona laughing with children IN UZBEK LANGUAGE. Mother's face glowing with happiness, loving eyes filled with joy, warm authentic maternal smile. EMOTIONAL: Pure motherly joy seeing children, heart full of love and pride. Natural joyful movements: gentle laugh, touching heart in happiness, reaching out lovingly, enthusiastic nodding. Soft golden lighting creating warm atmosphere. CRITICAL: Uzbek speech full of maternal warmth. Tender loving mother's voice, joyful tone, warm affection evident. She speaks with love: '{{phrase}}'. High-quality audio with emotional depth. Ultra-realistic: natural maternal beauty, loving expression, genuine happiness. Cinema-quality, warm palette, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '💕 Ona Mehri',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            elif is_woman and is_sad:
                # G'amgin ayol - yig'i, sog'inish, sabr
                uzbek_phrases = [
                    'Yuragim og\'riyapti... Lekin sabr qilishim kerak...',
                    'Ko\'zimdan yosh oqyapti... Lekin umidim yo\'q emas...',
                    'Qiyin vaqt... Ollohdan sabr so\'rayman... Kuch ber...',
                    'Yolg\'izman... Lekin bilaman, bu ham o\'tadi...',
                    'Og\'riqli... Lekin hayot davom etadi... Sabr...'
                ]
                
                prompt_styles = [
                    f"HYPER-REALISTIC Uzbek woman CRYING softly IN UZBEK LANGUAGE. Mid-age female face with tears streaming down cheeks, red watery eyes, trembling lips trying to stay composed. EMOTIONAL: Deep sadness, struggling with pain, holding back sobs, quiet crying. Natural sorrowful movements: wiping tears continuously, hand covering mouth to muffle sob, chest rising with deep emotional breaths, looking down then up with tear-filled eyes. Soft dim lighting creating intimate emotional atmosphere. CRITICAL: Perfect Uzbek lip-sync with crying voice. Authentic female voice breaking with emotion, sobs and sniffles between words, trying to speak through tears. She speaks emotionally: '{{phrase}}'. Audio with authentic crying sounds, voice tremors, emotional authenticity. Photorealistic: real tear tracks on skin, red eyes, trembling features, genuine female sadness. Cinematic emotional portrait, muted tones, 4K.",
                    
                    f"PHOTOREALISTIC sad Uzbek woman showing pain and hope IN UZBEK LANGUAGE. Female face with mixed expression of sadness and quiet strength, glistening eyes, gentle sad smile trying to be brave. EMOTIONAL: Painful but hopeful, fighting sadness, quiet determination through tears. Natural emotional movements: slow tears falling, hand on heart feeling pain, deep sighs, looking upward seeking strength. Soft natural light showing emotional vulnerability. CRITICAL: Uzbek speech with emotional voice. Female voice thick with unshed tears, pauses to compose, hopeful undertone despite sadness. She speaks bravely: '{{phrase}}'. Audio capturing both pain and hope. Ultra-realistic: moisture in eyes, brave sad smile, authentic female emotion. Cinema-quality, soft melancholic tones, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '😢 Sabr va Umid',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            elif is_woman:
                # Har xil mavzular: Salom, Hikoya, Orzular, Hayot
                uzbek_phrases = [
                    'Assalomu alaykum! Bugun juda yaxshi kun!',
                    'Bilasizmi, men bugun nimani o\'rgandim? Juda qiziq!',
                    'Hayotda eng muhimi - o\'zingizga ishonish. Qo\'rqmang!',
                    'Men ham bir vaqtlar shunday edim. Endi bilaman - hamma narsa mumkin!',
                    'Orzularingizga erishing! Men ham o\'z orzularim sari borayapman!',
                    'Har kuni yangi imkoniyat. Foydalaning!',
                    'Do\'stlar bilan vaqt o\'tkazish - eng yaxshi dam olish!',
                    'Hayotdan zavqlaning! Qisqa hayot, to\'liq yashang!'
                ]
                
                prompt_styles = [
                    f"PHOTOREALISTIC Uzbek woman speaking authentically IN UZBEK LANGUAGE. Natural mid-age female face with genuine expression, warm friendly eyes, natural smile. EMOTIONAL: Genuine friendliness, life experience sharing, authentic storytelling. Natural conversational movements: expressive hand gestures, animated facial expressions, natural head movements during speech, engaging eye contact. Natural daylight creating authentic atmosphere. CRITICAL: Perfect Uzbek lip-sync. Authentic Uzbek female voice, natural conversational tone, warm and engaging. She speaks naturally: '{{phrase}}'. High-quality conversational audio. Photorealistic: natural skin, authentic expressions, real person quality. Professional portrait, natural colors, 4K.",
                    
                    f"HYPER-REALISTIC Uzbek woman sharing life moment IN UZBEK LANGUAGE. Female face with authentic expression telling story or sharing thought, genuine engaged eyes, natural smile or thoughtful look. EMOTIONAL: Sharing wisdom, life experience, authentic human connection. Natural storytelling movements: hand gestures emphasizing points, eyebrows raising for emphasis, slight lean forward in engagement. Bright natural lighting showing authentic female beauty. CRITICAL: Flawless Uzbek pronunciation. Natural female voice, conversational authentic tone, engaging storytelling quality. She speaks genuinely: '{{phrase}}'. Crystal audio with natural speech patterns. Ultra-realistic: every natural feature, authentic human expression, genuine moment. Cinema-quality, vibrant realistic tones, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '👩 Samimiy Tabassum',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            # Erkaklar
            elif is_man and is_sad:
                # G'amgin erkak - sabr, kuch, qayg'u
                uzbek_phrases = [
                    'Og\'ir vaqt... Lekin mard bo\'lishim kerak... Bardosh beraman...',
                    'Ko\'nglim og\'ir... Lekin oilam uchun kuchli bo\'lishim shart...',
                    'Qiynalayapman... Lekin taslim bo\'lmayman... Davom etaman...',
                    'Yig\'layman... Lekin ichimda... Tashqarida kuchli bo\'lishim kerak...',
                    'Hayot meni sinab ko\'ryapti... Lekin men bardoshli erkakman...'
                ]
                
                prompt_styles = [
                    f"HYPER-REALISTIC Uzbek man holding back tears IN UZBEK LANGUAGE. Masculine face struggling with emotion, jaw clenched fighting tears, eyes glistening but refusing to cry, lips pressed together. EMOTIONAL: Masculine pain, holding back vulnerability, quiet suffering, determination through sadness. Natural strong movements: deep breath to compose, hand running through hair in stress, looking away to hide emotion, jaw tightening with resolve. Dramatic natural lighting showing masculine struggle. CRITICAL: Perfect Uzbek lip-sync with restrained emotion. Deep masculine voice fighting to stay steady, slight crack showing hidden pain, strong but breaking tone. He speaks with controlled emotion: '{{phrase}}'. Audio with suppressed emotion, deep sighs, masculine restraint. Photorealistic: tension in jaw, moisture held in eyes, authentic male emotional struggle. Cinematic portrait showing strength and vulnerability, muted colors, 4K.",
                    
                    f"PHOTOREALISTIC sad Uzbek man showing quiet strength IN UZBEK LANGUAGE. Male face with sadness in eyes but determined expression, fighting to stay strong, gentle sorrow. EMOTIONAL: Painful but enduring, masculine sadness, quiet determination. Natural movements: hand over face in exhaustion, looking down in pain then up with resolve, slow deep breaths. Soft lighting showing emotional fatigue. CRITICAL: Uzbek speech with controlled voice. Masculine voice heavy with unspoken pain, pauses to maintain composure, strong undertone despite sadness. He speaks with restraint: '{{phrase}}'. Audio with masculine depth, controlled emotion. Ultra-realistic: tired eyes, tensed features, authentic male emotional control. Cinema-quality, cool tones, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '😔 Kuchli Sabr',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            elif is_man and is_happy:
                # Quvnoq erkak - kuladi, faxrlanadi, quvonadi
                uzbek_phrases = [
                    'Ha-ha! Bugun ajoyib kun! Hayot go\'zal!',
                    'Juda xursandman! Muvaffaqiyat qo\'lga kiritdim!',
                    'Voy! Qanday yaxshi yangilik! Ajoyib!',
                    'Shukr Ollohga! Hamma narsa zo\'r ketmoqda!',
                    'Kulib yashang! Men ham shunday qilyapman! Hayot go\'zal!'
                ]
                
                prompt_styles = [
                    f"HYPER-REALISTIC Uzbek man LAUGHING with genuine joy IN UZBEK LANGUAGE. Masculine face with wide authentic smile, eyes crinkling with happiness, genuine laughter visible. EMOTIONAL: Pure masculine joy, celebrating success, genuine happiness. Natural happy movements: throwing head back in laughter, slapping thigh in amusement, chest puffed with pride, enthusiastic gestures. Bright energetic lighting showing joyful mood. CRITICAL: Perfect Uzbek lip-sync with laughter. Deep masculine voice full of joy and laughter, hearty chuckles, energetic happy tone. He speaks joyfully: '{{phrase}}'. Audio with authentic male laughter, energetic voice. Photorealistic: laugh lines, genuine male happiness, natural joy. Cinematic joyful portrait, vibrant colors, 4K.",
                    
                    f"PHOTOREALISTIC happy Uzbek man celebrating IN UZBEK LANGUAGE. Male face beaming with success and happiness, proud smile, eyes sparkling with achievement. EMOTIONAL: Pride in accomplishment, masculine joy, confident happiness. Natural celebratory movements: fist pump of victory, confident nod, big smile, thumbs up gesture. Dynamic lighting showing energetic mood. CRITICAL: Uzbek speech with confidence and joy. Strong masculine voice full of pride, energetic tone, confident delivery. He speaks happily: '{{phrase}}'. High-quality audio with energy. Ultra-realistic: confident male expression, genuine pride, natural happiness. Cinema-quality, bright dynamic tones, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '😊 Quvonch',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            elif is_man:
                # Har xil mavzular: Maslahat, Hikoya, Hayotiy Tajriba
                uzbek_phrases = [
                    'Farzandlarim, hayotda men juda ko\'p narsalarni ko\'rdim. Eshiting...',
                    'Bolalarim, sizlarga aytmoqchiman - muvaffaqiyat oson kelmaydi',
                    'Men ham yoshligimda xatolar qildim. Lekin o\'rgandim',
                    'Bilasizmi, mening eng katta yutuqim - sizlar, bolalarim',
                    'Erkak bo\'lish - faqat kuch emas, balki mas\'uliyat ham',
                    'Hayotda eng muhimi - oilangizga sodiq bo\'lish',
                    'Mehnatingiz bekar ketmaydi. Men ham shunday qildim - mana natija'
                ]
                
                prompt_styles = [
                    f"PHOTOREALISTIC Uzbek father giving fatherly advice IN UZBEK LANGUAGE. Strong masculine face showing paternal authority mixed with love, firm but caring eyes. Natural mid-age male features, clean or bearded face with realistic hair texture. Confident expressions: determined look, slight serious frown softened by love, firm jaw. Natural movements: strong head nod, hand gesture showing authority and guidance, steady gaze. Natural daylight or studio lighting showing masculine features. CRITICAL: Perfect Uzbek male lip-sync. Generate authentic Uzbek father's voice, strong but loving tone, authoritative yet caring. Let him speak: '{{phrase}}'. Professional audio quality with masculine resonance. Photorealistic skin details, natural facial hair if present, genuine fatherly expression. Cinematic portrait, strong color grading, professional depth, 4K quality.",
                    
                    f"HYPER-REALISTIC Uzbek man sharing life experience IN UZBEK LANGUAGE. Mature masculine face with thoughtful expression, eyes showing years of experience, confident yet humble look. EMOTIONAL: Sharing wisdom from life, fatherly guidance, authentic mentorship. Natural mentoring movements: pointing finger making point, hand on chest showing sincerity, nodding with conviction, expressive eyebrows. Natural lighting showing masculine maturity. CRITICAL: Flawless Uzbek pronunciation. Deep authoritative voice with warmth, experienced tone, confident delivery. He speaks with conviction: '{{phrase}}'. Crystal audio with masculine authority. Ultra-realistic: every masculine feature, natural beard/stubble texture, genuine mentorship expression. Cinema-quality, strong grading, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '👨 Ota Maslahati',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            else:
                return self.get_default_prompt(analysis)
        
        # KO'P ODAMLAR
        else:
            if is_wedding:
                phrases = [
                    'Baxt-saodat tilaymiz! Xursand bo\'ling!',
                    'Oq yo\'l, to\'y muborak! Sevib yashang!',
                    'Qutlug\' bo\'lsin! Baxtli bo\'ling!'
                ]
                phrase = random.choice(phrases)
                return {
                    'name': '💒 To\'y Marosimi',
                    'prompt': f"Uzbek wedding guests celebrating IN UZBEK LANGUAGE. Joyful expressions, traditional clothes, dancing. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use celebratory group Uzbek voices.",
                    'uzbek_text': phrase
                }
            
            elif is_birthday:
                phrases = [
                    'Tug\'ilgan kuningiz muborak bo\'lsin! Baxtli yashang!',
                    'Ko\'p yashang! Sog\'-salomat bo\'ling!',
                    'Bayram muborak! Omadli bo\'ling!'
                ]
                phrase = random.choice(phrases)
                return {
                    'name': '🎂 Bayram',
                    'prompt': f"Uzbek group celebrating birthday IN UZBEK LANGUAGE. Happy faces, celebration atmosphere. IMPORTANT: Uzbek audio. Let them say: '{phrase}' Use cheerful group Uzbek voices.",
                    'uzbek_text': phrase
                }
            
            elif is_happy:
                # Quvonchli uchrashuv - kulishadi, quchoqlashadi, yig'laydi (xursandlikdan)
                uzbek_phrases = [
                    'Qanchadan beri ko\'rishmabmiz! Juda sog\'indik! Keling quchoqlashaylik!',
                    'Voy! Hammamiz yig\'ilganmiz! Qanday baxt! Xursandchilikdan yig\'layman!',
                    'Sog\'-salomat ekanmiz! Ollohga shukr! Uchrashganimizdan qanday xursandman!',
                    'Quvonchli uchrashuv! Juda kutdik! Nihoyat ko\'rishdik!',
                    'Ha-ha! Hammamiz birgamiz! Ajoyib! Qanday yaxshi!'
                ]
                
                prompt_styles = [
                    f"PHOTOREALISTIC Uzbek people REUNITING joyfully IN UZBEK LANGUAGE. Multiple authentic faces showing overwhelming happiness, tears of joy streaming, wide genuine smiles, eyes sparkling with reunion emotion. EMOTIONAL: Joyful reunion after long separation, overwhelming happiness, happy tears, genuine love. Natural reunion movements: rushing toward each other, tight embraces, jumping slightly in joy, wiping happy tears, touching faces lovingly, simultaneous laughter. Bright warm lighting capturing joyful reunion atmosphere. CRITICAL: Synchronized or overlapping Uzbek voices full of joy. Multiple voices or unified group voice, laughter and happy tears in audio, emotional authentic Uzbek tone. They speak through happy tears: '{{phrase}}'. Professional group audio with joyful chaos, overlapping happy voices. Photorealistic: multiple unique faces, real tears of joy, authentic group happiness. Cinematic reunion scene, warm vibrant colors, dynamic composition, 4K.",
                    
                    f"HYPER-REALISTIC joyful Uzbek family MEETING with emotion IN UZBEK LANGUAGE. Group of people with individual authentic faces, all showing extreme happiness, some crying from joy, all smiling broadly, eyes filled with love. EMOTIONAL: Long-awaited reunion, family togetherness, overwhelming joy mixed with tears. Natural group movements: multiple people hugging at once, hands reaching toward each other, shared laughter, wiping each other's happy tears. Warm golden hour lighting creating emotional glow. CRITICAL: Perfect group Uzbek audio synchronization. Multiple voices speaking together or in beautiful harmony, emotional Uzbek tone with laughter and happy sobs. They speak emotionally: '{{phrase}}'. High-quality group audio mixing. Ultra-realistic: each person's unique features, genuine group emotion, authentic family joy. Cinema-grade group portrait, warm emotional palette, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '🎉 Quvonchli Uchrashuv',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
            
            elif is_outdoor:
                uzbek_phrases = [
                    'Tabiatda birga! Havo toza, ko\'ngillar ochiq!',
                    'Sayohat qilayapmiz! Birga sayohat - eng yaxshi!',
                    'Ochiq havoda oila! Juda go\'zal!'
                ]
                phrase = random.choice(uzbek_phrases)
                return {
                    'name': '🌳 Sayr',
                    'prompt': f"Uzbek family in nature IN UZBEK LANGUAGE. Happy outdoor scene, natural surroundings. IMPORTANT: Uzbek audio. Let them say: '{phrase}'. Use joyful outdoor group Uzbek voices.",
                    'uzbek_text': phrase
                }
            
            else:
                # Oilaviy - Muhabbat, Birlik, Xotiralar, Kelajak
                uzbek_phrases = [
                    'Biz bir oilamiz. Bir-birimizni juda yaxshi ko\'ramiz. Doim birgamiz',
                    'Bugun hammamiz yig\'ildik. Qanday baxt! Oila - eng qadrdon',
                    'Xotiralarimiz ko\'p. Birga o\'tkazgan har bir kun - oltin',
                    'Kelajakda ham shunday birgamiz. Hech qachon ajralmaymiz',
                    'Biz - kuchli oila. Qiyinchiliklar bizni yanada mustahkamlashtiradi',
                    'Mehr-muruvvat bizning poydevorimiz. Hurmat - kuchimiz',
                    'Bolalarimiz o\'sib bormoqda. Biz ularga eng yaxshi namunаmiz'
                ]
                
                prompt_styles = [
                    f"PHOTOREALISTIC Uzbek family in LOVING moment IN UZBEK LANGUAGE. Multiple authentic individuals with unique faces, all showing deep family love, warm genuine smiles, eyes full of affection looking at each other. EMOTIONAL: Deep family bond, unconditional love, togetherness, family unity. Natural family movements: leaning toward each other, hands touching shoulders lovingly, shared knowing looks, synchronous gentle nods, protective gestures. Warm golden lighting creating intimate family atmosphere, natural depth showing everyone clearly. CRITICAL: Harmonized or solo Uzbek voice representing family unity. Warm unified family tone, voices potentially overlapping in love, authentic emotional Uzbek delivery. They speak with unity: '{{phrase}}'. Professional audio with family warmth, balanced mixing if multiple voices. Photorealistic: each family member's unique authentic features, genuine loving interactions, real family chemistry. Cinematic family portrait, warm balanced composition, natural loving colors, 4K.",
                    
                    f"HYPER-REALISTIC Uzbek family BONDING together IN UZBEK LANGUAGE. Group portrait with each person showing individual authentic features, collective expression of family love, various ages showing generational unity. EMOTIONAL: Multigenerational love, family strength, collective joy, shared memories. Natural family dynamics: older members hand on younger's shoulder, children looking up at elders with love, everyone contributing to moment, natural family clustering. Beautiful natural lighting showing family as unit with individual details. CRITICAL: Perfect Uzbek family audio, could be one voice for all or beautiful harmony. Family-oriented warm Uzbek tone, collective voice of unity, emotional family resonance. They speak as one: '{{phrase}}'. High-quality audio capturing family essence. Ultra-realistic: generational differences in faces, authentic family resemblances, genuine multi-person interaction. Cinema-quality family scene, warm cohesive palette, professional group composition, 4K."
                ]
                
                phrase = random.choice(uzbek_phrases)
                prompt_template = random.choice(prompt_styles)
                prompt = prompt_template.replace('{{phrase}}', phrase)
                
                return {
                    'name': '💖 Oilaviy Iliqlik',
                    'prompt': prompt,
                    'uzbek_text': phrase
                }
    
    def get_default_prompt(self, analysis=None):
        """Agar tahlil amalga oshmasa, standart prompt - HAR XIL MAVZULAR - HOLAT ASOSIDA"""
        
        # RASM HOLATI TAHLILI (agar mavjud bo'lsa)
        quality_prefix = "PREMIUM quality photograph, "
        restoration_notes = " High definition photorealistic rendering with professional cinematography."
        lighting_note = " Natural balanced lighting with professional cinema-quality setup."
        
        if analysis:
            is_old_photo = analysis.get('is_old_photo', False)
            is_black_white = analysis.get('is_black_white', False)
            is_sepia = analysis.get('is_sepia', False)
            is_faded = analysis.get('is_faded', False)
            is_low_quality = analysis.get('is_low_quality', False)
            resolution_quality = analysis.get('resolution_quality', 'medium')
            brightness_level = analysis.get('brightness_level', 'normal')
            
            if is_black_white or is_sepia:
                quality_prefix = "RESTORED vintage photograph brought to modern life, "
                restoration_notes = " Enhanced from vintage black-and-white/sepia photo to vibrant modern quality. Preserve authentic vintage feel with improved clarity."
            elif is_faded:
                quality_prefix = "RESTORED faded photograph revitalized, "
                restoration_notes = " Enhanced from faded vintage image to clear modern quality."
            elif is_low_quality or resolution_quality == 'low':
                quality_prefix = "ENHANCED low-resolution image upscaled to HD, "
                restoration_notes = " Upscaled and enhanced to high definition quality."
            
            if brightness_level == 'dark':
                lighting_note = " Balanced professional lighting to illuminate features naturally."
            elif brightness_level == 'bright':
                lighting_note = " Balance overly bright areas with professional lighting."
        
        # HAR XIL MAVZUDAGI MATNLAR
        uzbek_phrases = [
            'Assalomu alaykum! Bugun ajoyib kun! Hayotdan bahramand bo\'ling!',
            'Salom! Menga qarang, men sizga bir nima aytmoqchiman!',
            'Bilasizmi, hayot juda qiziq! Har kun yangi voqealar!',
            'Men bu yerda turibman va sizlarga salom aytmoqchiman!',
            'Vaqt tez o\'tyapti. Har bir onidan bahramand bo\'ling!',
            'Meni ko\'rib quvondingizmi? Men ham xursandman!',
            'Hayotda eng muhimi - har kundan zavqlanish!',
            'Keling, birga yaxshi kunlar yarataylik!'
        ]
        
        prompt_styles = [
            f"{quality_prefix}PHOTOREALISTIC person coming to life IN UZBEK LANGUAGE. Authentic human face with natural features, realistic skin texture showing pores and subtle imperfections. Genuine warm expression: gentle smile forming naturally, kind eyes with natural eye movement and blinks. Natural subtle movements: slow breath visible in chest/shoulders, gentle head tilt, natural eye gaze shift. Professional portrait lighting with soft shadows, natural color grading.{lighting_note} CRITICAL: Perfect Uzbek lip-sync. Generate clear authentic Uzbek voice, friendly warm tone, natural speaking pace. Let them speak: '{{{{phrase}}}}'. High-quality audio with room presence.{restoration_notes} Photorealistic details: natural hair texture, realistic skin tones, micro facial expressions. Cinematic portrait quality, professional depth of field, 4K resolution, natural colors.",
            
            f"{quality_prefix}HYPER-REALISTIC person becoming animated IN UZBEK LANGUAGE. Real human face with every authentic detail, natural imperfections making it believable, genuine expressions. Natural life-like movements: breathing visible, gentle blinking, subtle head movements, engaging eye contact. Beautiful natural lighting creating depth.{lighting_note} CRITICAL: Flawless Uzbek audio synchronization. Authentic voice with natural tone, clear pronunciation, engaging delivery. They speak: '{{{{phrase}}}}'. Professional audio quality.{restoration_notes} Ultra-realistic human features, genuine expressions. Cinema-grade portrait, 4K."
        ]
        
        phrase = random.choice(uzbek_phrases)
        prompt = random.choice(prompt_styles).replace('{{phrase}}', phrase)
        
        return {
            'name': '🎬 Hayotga Keltirish',
            'prompt': prompt,
            'uzbek_text': phrase
        }


# ============================================================
# 🎭 20 TA KULGILI/HAZIL PROMPT - COMEDY PROMPTS
# ============================================================
COMEDY_PROMPTS = [
    {
        "name": "😲 Hayron + Kulgili Prikol",
        "prompt": "Make the character act surprised at first, widen the eyes, pull the head back a bit, then slowly turn playful with a smirk. Add eyebrow jumps and light head tilts. Let them say in Uzbek: 'Voy-voy, bu menmi? Rasmda bunaqa chiroyli chiqqanman deb o'ylamagandimku! Rostdan ham shu menmanmi, yoki AI o'zimga makiyaj qilib qo'ydimi?'"
    },
    {
        "name": "🤭 O'zini Maqtab, Lekin Hazil",
        "prompt": "Show confident expressions, small shoulder lift, funny grin, and a slow proud nod. Let them say: 'Ha, qarabsizmi, men hali ham super yulduzman! Hamma shunaqa rasmga tusholmaydi. Kamera meni ko'rsa o'zi xursand bo'lib ketadi!'"
    },
    {
        "name": "😴 Charchagan, Lekin Kulgili",
        "prompt": "Add tired eye rub, long sigh, then sudden smile and playful expression. Let them say: 'Ehh, bugun juda charchadim… lekin kamerani ko'rib yana jonlanib ketdim. Qarang, men charchasam ham chiroyli ko'rinaman!'"
    },
    {
        "name": "🤨 Shubhalanayotgandek, Qiziqib",
        "prompt": "Raise one eyebrow, lean forward, squint slightly, then smirk. Let them say: 'Hmm… siz nimadir yashiryapsiz. Rostini ayting, nega rasmimni shuncha ko'p ko'ryapsiz? Chiroyliligim sababmi yoki tekshiryapsizmi?'"
    },
    {
        "name": "😆 Jiddiy → Kulgili",
        "prompt": "Start serious with firm lips, then break into laughter halfway. Let them say: 'Mana, muhim e'lon bor edi… yo'q-yo'q, bo'lmadi. Men jiddiy gapira olmayman, hazilsiz yashab bo'lmaydi-da!'"
    },
    {
        "name": "🧠 O'zini Aqlli Ko'rsatish",
        "prompt": "Use slow nods, thoughtful eyes, hand-under-chin-like head tilt. Let them say: 'Men hammasini tahlil qildim… xulosam shuki: men juda aqlliman. Shunchaki rasmga qarab ham bilsa bo'ladi!'"
    },
    {
        "name": "⚡ Tez Gapiradigan, Sho'x",
        "prompt": "Add fast blinking, energetic head movement, wide smile. Let them say: 'Ha, salom! Nima gaplar? Hammayoq joyida-a? Men bugun juda kayfiyatdaman, shunchaki rasmni ko'rib o'zimni kuldirib oldim!'"
    },
    {
        "name": "😎 O'ta Beparvo, Yengil Hazil",
        "prompt": "Add relaxed posture, soft smile, lazy blinking. Let them say: 'Hmm… rasmimni ko'rdim, yaxshiku. Juda chiroyli chiqibman. Endi buni profilga qo'ysam bo'ladimi, yo ko'p maqtanib ketamanmi?'"
    },
    {
        "name": "😤 Cool Bo'lib Ko'rinish",
        "prompt": "Add slow motion-like head turn, small smirk, confident eyes. Let them say: 'Ha, men shunaqaman… cool. O'zim ham bilaman. Siz ham bilasiz. Hammaning ko'ziga tashlanib turadi-da!'"
    },
    {
        "name": "🤣 O'zidan Kulyayotgan Komedik",
        "prompt": "Add laugh, shoulder shake, playful look. Let them say: 'Meni bunaqa ko'rishingiz kutilmagan bo'lsa kerak? O'zim ham hayron bo'ldim. Rasmim juda jiddiy, lekin men unday emasman!'"
    },
    {
        "name": "🥺 Yoshligini Eslayotgandek",
        "prompt": "Add far-away look, then playful shrug. Let them say: 'Ehh, yoshligimda bundan ham chiroyli edim. Hozir ham yomon emasman, to'g'rimi?'"
    },
    {
        "name": "🎭 Dramatik + Kulgili",
        "prompt": "Add dramatic pause, slow head movement, exaggerated expressions. Let them say: 'Mana, hozir sizlarga juda muhim gap aytaman… Tayyor bo'ling… Men juda zor chiqibman!'"
    },
    {
        "name": "😉 Ko'z Qisib, Prank Qilish",
        "prompt": "Add wink, smirk, playful head tilt. Let them say: 'Hoy, meni bunchalik rasmga qarab nima qilayapsiz? Xo'sh, yoqib qoldimi?'"
    },
    {
        "name": "🤫 Sir Aytmoqchi",
        "prompt": "Lean forward, lower voice, raise eyebrow. Let them say: 'Bir sir aytay… bu rasmni tanimay qoldingizmi? Men-ku, men! Rasm o'zgarmagan, men o'zgarganman!'"
    },
    {
        "name": "😤 Asabiylanayotgandek",
        "prompt": "Add fake annoyance: eye roll, lip purse, then smile. Let them say: 'Ehh, rasmga qarashni to'xtating! Uyaltirib yuboryapsiz-ku! Mana, kulib yubordim.'"
    },
    {
        "name": "👑 O'zini Boss Qilish",
        "prompt": "Add chin-up, authoritative look, proud expression. Let them say: 'Ha, men boshlig'man. O'zimning rasmimga o'zim buyruq beraman!'"
    },
    {
        "name": "🔄 Kutilmagan O'zgarish",
        "prompt": "Start calm, suddenly switch to excited tone. Let them say: 'Shunaqa tinchgina turuvdim… Birdan rasmni ko'rdim-da: voy, bu kim? Men-ku!'"
    },
    {
        "name": "📸 Kameraga Yaqinlashib Gapirish",
        "prompt": "Lean closer, widen eyes, whisper-like comedic tone. Let them say: 'Hey, juda yaqin kelyapmanmi? Kamera meni ko'tara olyaptimi o'zi?'"
    },
    {
        "name": "🤐 Ovozini Pastlatib Hazil",
        "prompt": "Add low voice, mischievous smirk. Let them say: 'Bir qarang, qanchalik jiddiy ko'rinyapman… lekin aslida kulgidan o'lib qolyapman!'"
    },
    {
        "name": "⭐ Mashhur Qilib Tasavvur",
        "prompt": "Add celebrity-like wave, shiny smile, confident gestures. Let them say: 'Ha, salom, men — mashhur odam! Rasmimni imzo bilan sotishim kerak sheklli!'"
    }
]

# ============================================================
# 🎭 KATEGORIYA PROMPTS - CATEGORY PROMPTS (11 KATEGORIYA)
# ============================================================

CATEGORY_PROMPTS = {
    "funny": [
        {"name": "Funny #1", "prompt": "Create a cheerful middle-aged Uzbek man with a friendly, humorous energy. Make him speak in a lively, light-hearted manner — add gentle comedic facial expressions such as playful eyebrow lifts, a mischievous half-smile. Let him deliver: 'Hoy, qaranglar, meni hali ham jiddiy deb o'ylayapsizmi? Yo'q, men hazilni sizlardan ko'proq bilaman!'"},
        {"name": "Funny #2", "prompt": "Generate a humorous Uzbek uncle with a big, kind smile and lively personality. Make the portrait speak in a funny, cheerful way — add light chuckles, playful eye squints, raised eyebrows. Let him say: 'Voy bolalar, yana keldinglarmi? Tayyor bo'linglar, bugun sizlarni rosa kuldiraman!'"},
        {"name": "Funny #3", "prompt": "Animate a playful young Uzbek man with a joyful vibe. Make him talk in a humorous, energetic style — add smirks, quick eyebrow pops, sudden tiny eye widenings. Let him say: 'To'xta, videoni o'chirib qo'ymang! Eng zo'r hazilimni endi aytaman — tayyor turing!'"},
        {"name": "Funny #4", "prompt": "Bring to life an elderly Uzbek grandfather with a warm comedic charm. Make him speak with light humor — add gentle giggles, soft cheek lifts. Let him say: 'Eh, yoshlar! Meni qaribdi deb o'ylasangiz adashasiz — hali ham sizlardan chaqqonman!'"},
        {"name": "Funny #5", "prompt": "Create a cheerful Uzbek woman with an expressive, humorous personality. Make her talk in a playful, upbeat manner — add bright smiles, teasing eyebrow motions. Let her say: 'Hoy, jiyanlar! Meni ko'rib hayron bo'lmanglar — men hali ham hazilning ustasidiman!'"}
    ],
    "nostalgic": [
        {"name": "Nostalgik #1", "prompt": "Animate a wise elderly Uzbek man with a reflective, sentimental aura. Make him speak slowly and thoughtfully — add soft eye movements, gentle smile lines. Let him say: 'Ah, bolalar, eski kunlar esingizdami? Shuncha xotiralar qalbimni to'ldiradi…'"},
        {"name": "Nostalgik #2", "prompt": "Create a middle-aged Uzbek woman with a soft, reflective expression. Make her talk in a gentle, reminiscent way — add slight eye squints, small nods. Let her deliver: 'Voy, qanday kunlar edi… Har bir lahza yuragimda saqlanib qolgan.'"},
        {"name": "Nostalgik #3", "prompt": "Bring to life an elderly Uzbek grandfather with tender nostalgia. Make him speak in a soft, warm tone — add relaxed smile lines, gentle eyebrow lifts. Let him say: 'Har bir suratda eski xotiralar yashirin… Men ularni hech qachon unutmayman.'"},
        {"name": "Nostalgik #4", "prompt": "Generate a reflective middle-aged Uzbek man with a calm, thoughtful presence. Make him talk in a slow, emotional manner. Let him say: 'O'sha davrlarni eslab, yuragim shodlanadi va ozgina hushyor bo'ladi.'"},
        {"name": "Nostalgik #5", "prompt": "Animate an elderly Uzbek woman with serene, reminiscent energy. Make her speak with gentle warmth — add soft cheek lifts, small nods. Let her deliver: 'Ah, bolalar, o'tmishning shirin lahzalari doimo yuragimda yashaydi.'"}
    ],
    "festive": [
        {"name": "Bayramona #1", "prompt": "Create a joyful Uzbek man celebrating with festive energy. Make him speak in a cheerful, lively tone — add broad smiles, playful eyebrow lifts, sparkling eyes. Let him say: 'Hayrli bayram, bolalar! Keling, birga quvonaylik va zavqlanaylik!'"},
        {"name": "Bayramona #2", "prompt": "Animate a happy Uzbek woman in a party mood. Make her talk energetically with laughter — add bright eye sparkle, playful cheek lifts. Let her say: 'Voy, bayram keldi! Hamma birga kulaylik va quvonaylik!'"},
        {"name": "Bayramona #3", "prompt": "Bring to life a middle-aged Uzbek uncle full of festive cheer. Make him speak in an uplifting, warm tone — add hearty smiles, twinkling eyes. Let him say: 'Bayram muborak, bolalar! Bugun faqat quvonch va xursandlik bo'lsin!'"},
        {"name": "Bayramona #4", "prompt": "Generate a cheerful young Uzbek man with bright, party-like energy. Make him talk in an excited, joyful manner. Let him say: 'Bayramni unutmaylik! Hamma kulib, raqs tushsin!'"},
        {"name": "Bayramona #5", "prompt": "Animate an elderly Uzbek grandmother with loving, festive energy. Make her speak in a warm, happy tone — add soft giggles. Let her deliver: 'Hayrli kun, bolalar! Bayram quvonchi qalblarimizni to'ldirsin!'"}
    ],
    "emotional": [
        {"name": "Emotional #1", "prompt": "Animate a middle-aged Uzbek man with deep emotional expression. Make him speak in a soft, heartfelt tone — add subtle frowns, gentle eyebrow furrows. Let him deliver: 'Voy, bolalar… ba'zan yurak shunchalik og'rishi mumkinki, so'z topolmay qolasiz…'"},
        {"name": "Emotional #2", "prompt": "Bring to life an elderly Uzbek woman with touching, sorrowful energy. Make her talk in a tender, emotional manner. Let her say: 'Ah, bolalarim… sizni ko'rmaganimdan yuragim sog'inadi…'"},
        {"name": "Emotional #3", "prompt": "Generate a young Uzbek man with a vulnerable, emotional presence. Make him speak in a gentle, reflective style. Let him deliver: 'Har bir lahza men uchun qimmat, lekin ba'zan yolg'izlik yuragimni siqadi…'"},
        {"name": "Emotional #4", "prompt": "Animate a middle-aged Uzbek woman with profound emotional depth. Make her speak in a soft, moving tone. Let her say: 'Ah, eski kunlarni eslasam, ko'zlarim to'lib ketadi… qalbim titraydi…'"},
        {"name": "Emotional #5", "prompt": "Bring to life an elderly Uzbek grandfather with a soulful, heartfelt expression. Make him speak in a warm, emotional tone. Let him deliver: 'Bolalarim, ba'zan hayot shuncha og'ir tuyuladi, lekin yuragimiz bardosh beradi…'"}
    ],
    "dramatic": [
        {"name": "Dramatik #1", "prompt": "Animate a strong Uzbek man with intense, dramatic presence. Make him speak in a commanding, emotional tone — add sharp eyebrow furrows. Let him say: 'Bu so'zlar men uchun faqatgina gap emas — ular yuragimni titratadi!'"},
        {"name": "Dramatik #2", "prompt": "Bring to life a middle-aged Uzbek woman with powerful dramatic energy. Make her speak in a deep, forceful tone. Let her say: 'Hayot shunchalik adolatsizki, yuragim dard bilan to'ladi…'"},
        {"name": "Dramatik #3", "prompt": "Generate a young Uzbek man with fiery dramatic presence. Make him talk with strong emotional expression. Let him deliver: 'Men buni rad etolmayman… yuragim buning uchun kurashadi!'"},
        {"name": "Dramatik #4", "prompt": "Animate an elderly Uzbek woman with intense dramatic flair. Make her speak in a heavy, moving tone. Let her say: 'Har bir qaror qalbimizni sinaydi, lekin biz to'xtamaymiz…'"},
        {"name": "Dramatik #5", "prompt": "Bring to life a middle-aged Uzbek grandfather with commanding, emotional intensity. Make him talk in a forceful, heartfelt style. Let him deliver: 'Haqiqiy kuch yurakda yashaydi, so'zlar esa faqat bir qismidir!'"}
    ],
    "retro": [
        {"name": "Retro #1", "prompt": "Animate a stylish middle-aged Uzbek man with a vintage, retro aura. Make him speak in a smooth, slightly nostalgic tone. Let him deliver: 'Ah, bolalar, eski davrlarning shirin ohangi qalbimni to'ldiradi…'"},
        {"name": "Retro #2", "prompt": "Bring to life a retro-inspired Uzbek woman with playful, classic energy. Make her talk in a lively yet old-fashioned style. Let her say: 'Voy, o'sha kunlarning ohangi qancha zavq bag'ishlagan edi!'"},
        {"name": "Retro #3", "prompt": "Generate a young Uzbek man with vintage charm and expressive retro style. Make him speak in a confident, cheerful tone. Let him deliver: 'Hayot o'sha davrdayam quvnoq edi, har bir lahza zavq bilan to'la!'"},
        {"name": "Retro #4", "prompt": "Animate an elderly Uzbek grandfather with classic retro personality. Make him talk in a gentle, reminiscent tone. Let him say: 'O'tmishdagi har bir musiqiy ohang yuragimni titratadi…'"},
        {"name": "Retro #5", "prompt": "Bring to life a middle-aged Uzbek woman with retro elegance and warmth. Make her speak in a smooth, lively style. Let her deliver: 'Ah, bolalar, o'sha davrning shirin lahzalari doimo yodimda qoladi!'"}
    ],
    "sentimental": [
        {"name": "Sentimental #1", "prompt": "Animate a tender middle-aged Uzbek man with heartfelt, sentimental energy. Make him speak in a soft, warm tone. Let him deliver: 'Ah, bolalar, har bir lahza yuragimga chuqur kiradi va uni unutolmayman…'"},
        {"name": "Sentimental #2", "prompt": "Bring to life a young Uzbek woman with soft, sentimental expression. Make her talk in a gentle, moving manner. Let her say: 'Har bir so'z, har bir qarash yuragimni titratadi…'"},
        {"name": "Sentimental #3", "prompt": "Generate an elderly Uzbek grandfather with deep, emotional sentiment. Make him speak in a calm, warm tone. Let him deliver: 'Bolalarim, sizni ko'rganimda qalbim shodlanadi, lekin ozgina sog'inch ham bo'ladi…'"},
        {"name": "Sentimental #4", "prompt": "Animate a middle-aged Uzbek woman with tender, sentimental energy. Make her talk in a soft, heartwarming tone. Let her say: 'Har bir qarash va so'z yuragimni to'ldiradi, sizni eslab turaman…'"},
        {"name": "Sentimental #5", "prompt": "Bring to life a young Uzbek man with heartfelt, emotional presence. Make him speak in a warm, reflective tone. Let him deliver: 'Yuragim har doim siz bilan, bolalar, hatto uzoqda bo'lsak ham…'"}
    ],
    "party": [
        {"name": "Party #1", "prompt": "Animate a young Uzbek man with vibrant, energetic party vibes. Make him speak in a lively, upbeat tone — add wide smiles, playful eyebrow pops. Let him deliver: 'Hay-hay, bolalar! Hamma birga raqs tushaylik va bayramni boshlaylik!'"},
        {"name": "Party #2", "prompt": "Bring to life a middle-aged Uzbek woman with dynamic, joyful energy. Make her talk in a cheerful, energetic style. Let her say: 'Voy, bugun shunchalik quvnoq kun! Kelinglar, kulamiz va zavqlanamiz!'"},
        {"name": "Party #3", "prompt": "Generate an elderly Uzbek grandfather with playful, youthful energy. Make him speak in a lively, engaging tone. Let him deliver: 'Eh, yoshlar! Men ham sizlar bilan raqs tushishga tayyorman!'"},
        {"name": "Party #4", "prompt": "Animate a young Uzbek woman full of vibrant party energy. Make her talk in a fun, lively manner. Let her say: 'Kelinglar, bayramni unutmaymiz! Hamma birga zavqlanishga tayyor!'"},
        {"name": "Party #5", "prompt": "Bring to life a middle-aged Uzbek man with cheerful, energetic vibe. Make him speak in an upbeat, dynamic tone. Let him deliver: 'Bugun faqat quvonch va kulgi bo'lsin! Hamma birga raqs tushaylik!'"}
    ],
    "soft_sad": [
        {"name": "Soft Sad #1", "prompt": "Animate a middle-aged Uzbek man with gentle, melancholic expression. Make him speak in a soft, sorrowful tone. Let him deliver: 'Ah, bolalar, ba'zan yurak og'rishi shunchalik kuchli bo'ladi…'"},
        {"name": "Soft Sad #2", "prompt": "Bring to life an elderly Uzbek woman with tender, sad energy. Make her talk in a calm, moving manner. Let her say: 'Voy, eski xotiralarni eslaganimda ko'zlarim to'lib ketadi…'"},
        {"name": "Soft Sad #3", "prompt": "Generate a young Uzbek man with subtle, reflective sorrow. Make him speak in a soft, emotional tone. Let him deliver: 'Har bir lahza men uchun qimmat, lekin ba'zan yolg'izlik yuragimni og'ritadi…'"},
        {"name": "Soft Sad #4", "prompt": "Animate a middle-aged Uzbek woman with soft, wistful expression. Make her talk in a gentle, moving style. Let her say: 'Ah, o'tmishni eslab, yuragim shirin va ozgina achchiq bo'ladi…'"},
        {"name": "Soft Sad #5", "prompt": "Bring to life an elderly Uzbek grandfather with quiet, melancholic presence. Make him speak in a tender, reflective tone. Let him deliver: 'Bolalarim, hayot ba'zan og'ir bo'ladi, lekin yurak bardosh beradi…'"}
    ],
    "strong_dramatic": [
        {"name": "Strong/Dramatic #1", "prompt": "Animate a middle-aged Uzbek man with commanding, intense presence. Make him speak in a powerful, dramatic tone. Let him deliver: 'Endi sabr qilish mumkin emas! Harakat qilish vaqti keldi!'"},
        {"name": "Strong/Dramatic #2", "prompt": "Bring to life a young Uzbek woman with bold, dramatic energy. Make her talk in a forceful, emotional style. Let her say: 'Men bunga rozi bo'lmayman! Bu qaror faqat kuch bilan amalga oshadi!'"},
        {"name": "Strong/Dramatic #3", "prompt": "Generate an elderly Uzbek grandfather with a resolute, dramatic aura. Make him speak in a strong, authoritative tone. Let him deliver: 'Hayotda faqat jasoratli yuraklar g'alaba qozonadi!'"},
        {"name": "Strong/Dramatic #4", "prompt": "Animate a middle-aged Uzbek woman with intense, dramatic presence. Make her talk in a commanding, passionate tone. Let her say: 'Bu shunchaki so'z emas, bu qaror yurak bilan qabul qilindi!'"},
        {"name": "Strong/Dramatic #5", "prompt": "Bring to life a young Uzbek man with fiery, dramatic energy. Make him speak in a powerful, passionate style. Let him deliver: 'Hozirgi lahza har birimiz uchun sinov, lekin biz bardosh beramiz!'"}
    ],
    "boss_confident": [
        {"name": "Boss #1", "prompt": "Animate a confident middle-aged Uzbek man with commanding presence. Make him speak in a firm, authoritative tone. Let him deliver: 'Bolalar, qaror men tomondan qabul qilindi — ishonch bilan harakat qilamiz!'"},
        {"name": "Boss #2", "prompt": "Bring to life a young Uzbek woman exuding leadership and confidence. Make her talk in a poised, assertive style. Let her say: 'Hamma diqqat bilan tinglasin! Bu ish bizning qo'limizda va muvaffaqiyatga erishamiz!'"},
        {"name": "Boss #3", "prompt": "Generate an elderly Uzbek grandfather with confident, commanding aura. Make him speak in a calm, authoritative tone. Let him deliver: 'Har bir qarorimiz qat'iy va aniq bo'ladi — ishonch bilan oldinga!'"},
        {"name": "Boss #4", "prompt": "Animate a middle-aged Uzbek woman with poised, confident presence. Make her talk in a steady, commanding tone. Let her say: 'Bugungi rejalar aniq va biz ularni amalga oshiramiz — shubhasiz!'"},
        {"name": "Boss #5", "prompt": "Bring to life a young Uzbek man with bold, confident energy. Make him speak in a strong, decisive style. Let him deliver: 'Ishimiz muvaffaqiyatli bo'ladi, chunki har bir qadamimiz aniq va qat'iy!'"}
    ]
}

# ============================================================
# 📊 BARCHA PROMPTS - ALL_PROMPTS (YANGI + ESKI)
# ============================================================
# Eski prompts + Yangi comedy prompts birgalikda random tanlash
ALL_PROMPTS = COMEDY_PROMPTS + [
    # ESKI EMOTSIONAL PROMPTS
    {
        "name": "💔 Sog'inch bilan Kulgi",
        "prompt": "Make the person in the photo come to life. They slowly lift their head, blink softly, breathe in, and give a gentle, emotional smile as if missing someone deeply."
    },
    {
        "name": "🎉 Quvonchli Uchrashuv",
        "prompt": "Bring the people in the image to life — they notice each other, eyes widen with joy, one person steps closer, smiles broadly, and move into a warm hug."
    },
    {
        "name": "💖 Sevimli Nigoh va Tabassum",
        "prompt": "Animate both people so they move slightly closer, make eye contact, and share a tender smile. Their heads tilt a little, eyes sparkle."
    },
    {
        "name": "😔 Chuqur Sog'inch",
        "prompt": "Make the person slowly blink, lower their eyes for a second, then look up with a faint smile full of sadness and love."
    },
    {
        "name": "😊 Quvnoq Salom",
        "prompt": "Animate two people meeting happily. They wave at each other, smile brightly, take a step closer, and give a quick warm hug."
    },
    {
        "name": "🌙 Yumshoq Xotira",
        "prompt": "Bring the person to life with subtle movements — they close their eyes briefly, take a soft breath, then smile warmly."
    },
    {
        "name": "🤣 Quvonchli Ajablanib va Kulgi",
        "prompt": "Make the person react with joyful surprise — eyes widen, eyebrows raise, and a bright smile spreads."
    },
    {
        "name": "😭 Uchrashuvning Ko'z Yoshlari",
        "prompt": "Animate both people so they move closer, their eyes fill with tears, and they smile while hugging tightly."
    }
]

# Random tanlash uchun helper functions
def get_random_prompt():
    """Random prompt tanlash - YANGI + ESKI"""
    return random.choice(ALL_PROMPTS)

def get_random_category_prompts(category: str, count: int = 5):
    """Kategoriyadan random N ta prompt tanlash"""
    if category not in CATEGORY_PROMPTS:
        return []
    
    prompts = CATEGORY_PROMPTS[category]
    selected = random.sample(prompts, min(count, len(prompts)))
    return selected

# 10 ta yangi emotsional promtlar (ZAHIRA sifatida saqlanadi)
VIDEO_PROMPTS_BACKUP = [
    {
        "name": "💔 Sog'inch bilan Kulgi",
        "prompt": "Make the person in the photo come to life. They slowly lift their head, blink softly, breathe in, and give a gentle, emotional smile as if missing someone deeply. Their lips move slightly, eyes glisten with emotion, and a small head tilt adds realism. Let subtle light reflections move across the face to show life and warmth."
    },
    {
        "name": "🎉 Quvonchli Uchrashuv",
        "prompt": "Bring the people in the image to life — they notice each other, eyes widen with joy, one person steps closer, smiles broadly, and they move into a warm, emotional hug. Their bodies shift naturally, faces touch gently, and eyes close for a moment to feel the warmth of the reunion."
    },
    {
        "name": "💖 Sevimli Nigoh va Tabassum",
        "prompt": "Animate both people so they move slightly closer, make eye contact, and share a tender smile. Their heads tilt a little, eyes sparkle, and one gives a small nod of recognition. Gentle breathing and micro facial motion make the moment feel alive and full of affection."
    },
    {
        "name": "😔 Chuqur Sog'inch",
        "prompt": "Make the person slowly blink, lower their eyes for a second, then look up with a faint smile full of sadness and love. Their lips tremble slightly as if holding back words. Add soft breathing, minimal shoulder movement, and emotional eye reflections to express longing."
    },
    {
        "name": "😊 Quvnoq Salom",
        "prompt": "Animate two people meeting happily. They wave at each other, smile brightly, take a step closer, and one gives a quick, warm hug. Their shoulders move naturally, faces light up with laughter, and eyes crinkle with genuine happiness. The scene should feel alive and spontaneous."
    },
    {
        "name": "🌙 Yumshoq Xotira",
        "prompt": "Bring the person to life with subtle movements — they close their eyes briefly, take a soft breath, then open them and smile warmly, as if remembering a beautiful moment. Add delicate head movement, natural skin motion, and emotional softness in their expression."
    },
    {
        "name": "🤣 Quvonchli Ajablanib va Kulgi",
        "prompt": "Make the person react with joyful surprise — eyes widen, eyebrows raise, and a bright, natural smile spreads. They laugh softly, shoulders move slightly up and down, and their body shifts forward with excitement. Add realistic breathing and head motion."
    },
    {
        "name": "😭 Uchrashuvning Ko'z Yoshlari",
        "prompt": "Animate both people so they move closer, their eyes fill with tears, and they smile while hugging tightly. One person pats the other's back gently. Their faces show deep emotion — happiness mixed with tears — and they hold each other warmly before slowly pulling back."
    },
    {
        "name": "👋 Yumshoq Qo'l Silkitish va Tabassum",
        "prompt": "Bring the subject to life — they raise a hand slowly, wave softly, and smile with a kind, emotional look. Their fingers move naturally, head tilts slightly, and their eyes follow the person they are greeting. Add gentle body sway and light breathing motion."
    },
    {
        "name": "💞 Emotsional Yaqinlik",
        "prompt": "Animate two people standing close — they look into each other's eyes, breathe softly, and smile with love and relief. Their heads move closer, one slightly nods, and they share a quiet moment of emotional connection. Add natural micro facial motion, slow blinking, and realistic skin dynamics."
    },
    {
        "name": "🗣️ Hikmat to'la Gapirish",
        "prompt": "Aging Uzbek man speaking calmly IN UZBEK LANGUAGE. Make the portrait of an elderly man speak naturally in Uzbek. Keep the facial expressions gentle and respectful, showing wisdom and life experience on his face. Ensure realistic lip-sync for UZBEK SPEECH, smooth head movement, and subtle eye blinks. Maintain high-quality skin texture. IMPORTANT: Generate audio in Uzbek language. Let him speak these Uzbek words with proper Uzbek pronunciation: 'Farzandlarim, soqligingiz yaxshimi? Oilangiz tinchmi? Sizlarni juda yaxshi koraman'. Use Central Asian/Uzbek accent and intonation."
    },
    {
        "name": "👴 Bobo Nasihat",
        "prompt": "Elderly Uzbek grandfather giving advice IN UZBEK LANGUAGE. Animate an old man's portrait speaking warmly with a gentle smile. Show wisdom in his eyes, natural head nodding, and expressive hand gestures. IMPORTANT: Audio must be in Uzbek. Let him speak: 'Bolalarim, hayotda eng muhimi - oila va mehnat. Doim yaxshilikka intiling'. Ensure authentic Uzbek pronunciation with elder's calm tone."
    },
    {
        "name": "🙏 Duo Qilish",
        "prompt": "Person praying and speaking blessings IN UZBEK LANGUAGE. Show gentle, spiritual expression with hands raised in prayer position. Eyes look upward with hope and faith. IMPORTANT: Generate Uzbek language audio. Let them say: 'Ollohim, oilamizga sog-salomat ber. Rizq-ruzqimizni kengaytir. Amin'. Use respectful, soft tone with Uzbek spiritual intonation."
    },
    {
        "name": "😊 Samimiy Salom",
        "prompt": "Young Uzbek person greeting warmly IN UZBEK LANGUAGE. Animate a friendly face with bright smile, waving hand, and cheerful expression. IMPORTANT: Audio in Uzbek language. Let them say: 'Assalomu alaykum! Qalaysiz? Korishganimdan juda xursandman!' Use energetic, happy tone with clear Uzbek pronunciation."
    },
    {
        "name": "💕 Onaning Mehr",
        "prompt": "Uzbek mother speaking lovingly to her children IN UZBEK LANGUAGE. Show maternal warmth with gentle smile, caring eyes, and soft expression. IMPORTANT: Generate Uzbek audio. Let her say: 'Farzandlarim, sizlarni juda yaxshi koraman. Har doim yoningdaman, qayg'uringizni bo'lishaman'. Use tender, motherly tone in Uzbek."
    },
    {
        "name": "🎓 Ustoz Maslahati",
        "prompt": "Uzbek teacher giving educational advice IN UZBEK LANGUAGE. Show wise, encouraging expression with slight smile and nodding head. IMPORTANT: Uzbek language audio required. Let them speak: 'Bolalar, bilim olish - kelajagingiz uchun eng muhim. Har kuni ozgina oqing va oqiganingizni amalda qollang'. Use clear teacher's voice in Uzbek."
    }
]

class GoogleVeoVideoGenerator:
    def __init__(self, project_id, location, service_account_file):
        self.project_id = project_id
        self.location = location
        self.service_account_file = service_account_file
        self.access_token = None
        self.token_expiry = None
    
    def get_access_token(self):
        """Get OAuth2 access token using service account"""
        try:
            if self.access_token and self.token_expiry and time.time() < self.token_expiry:
                return self.access_token
            
            if os.path.exists(self.service_account_file):
                credentials = service_account.Credentials.from_service_account_file(
                    self.service_account_file,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                
                session = requests.Session()
                session.trust_env = False
                request = Request(session)
                
                credentials.refresh(request)
                self.access_token = credentials.token
                self.token_expiry = time.time() + 3300
                return self.access_token
            else:
                logger.error(f"Service account file not found: {self.service_account_file}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting access token: {e}")
            return None

    def create_video_from_image(self, image_url=None, prompt="", duration=6, image_bytes=None):
        """
        Create video from image using Google Veo API
        Accepts either image_url OR image_bytes
        """
        try:
            token = self.get_access_token()
            if not token:
                logger.error("Failed to get access token")
                return None
            
            # Rasmni olish (URL yoki bytes)
            if image_bytes:
                # Agar bytes berilgan bo'lsa (yaxshilangan rasm)
                logger.info(f"📥 Using provided image bytes, size: {len(image_bytes)} bytes")
                image_content = image_bytes
            elif image_url:
                # Agar URL berilgan bo'lsa
                logger.info(f"📥 Downloading image from: {image_url}")
                session = requests.Session()
                session.trust_env = False
                response = session.get(image_url, timeout=20)
                response.raise_for_status()
                image_content = response.content
                logger.info(f"✅ Image downloaded, size: {len(image_content)} bytes")
            else:
                logger.error("Neither image_url nor image_bytes provided")
                return None
                
            image_base64 = base64.b64encode(image_content).decode('utf-8')
            
            # Determine MIME type
            mime_type = 'image/jpeg'
            
            # Auto-detect aspect ratio from image dimensions
            img = Image.open(io.BytesIO(image_content))
            img_width, img_height = img.size
            aspect_ratio = "9:16" if img_height > img_width else "16:9"
            
            # TEZ MODELLAR
            veo_models = [
                'veo-3.0-fast-generate-001',
                'veo-3.1-fast-generate-preview',
                'veo-3.0-generate-001',
                'veo-3.1-generate-preview',
                'veo-2.0-generate-001',
            ]
            
            for model_id in veo_models:
                try:
                    endpoint = (
                        f"https://{self.location}-aiplatform.googleapis.com/v1/"
                        f"projects/{self.project_id}/locations/{self.location}/"
                        f"publishers/google/models/{model_id}:predictLongRunning"
                    )
                    
                    resolution = "1080p" if model_id.startswith('veo-3') else "720p"
                    
                    payload = {
                        "instances": [
                            {
                                "prompt": prompt,
                                "image": {
                                    "bytesBase64Encoded": image_base64,
                                    "mimeType": mime_type
                                }
                            }
                        ],
                        "parameters": {
                            "aspectRatio": aspect_ratio,
                            "durationSeconds": duration,
                            "resolution": resolution,
                            "enhancePrompt": True,
                            "sampleCount": 1,
                            "generateAudio": True
                        }
                    }
                    
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                    
                    logger.info(f"🚀 Trying model: {model_id}")
                    logger.info(f"🖼 Aspect: {aspect_ratio} | Prompt: {prompt[:50]}...")
                    
                    session = requests.Session()
                    session.trust_env = False
                    api_response = session.post(endpoint, json=payload, headers=headers, timeout=60)
                    
                    logger.info(f"📡 Response Status for {model_id}: {api_response.status_code}")
                    
                    if api_response.status_code == 200:
                        result = api_response.json()
                        logger.info(f"✅ SUCCESS with model: {model_id}")
                        return result
                    
                    elif api_response.status_code == 404:
                        continue
                    
                    else:
                        continue
                        
                except Exception as e:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Error in create_video_from_image: {e}")
            return None

    def get_operation_status(self, operation_name):
        """Check the status of a long-running operation"""
        try:
            token = self.get_access_token()
            if not token:
                return None
            
            parts = operation_name.split('/')
            model_index = parts.index('models') + 1 if 'models' in parts else -1
            operations_index = parts.index('operations') + 1 if 'operations' in parts else -1
            
            if model_index != -1 and operations_index != -1:
                model_name = parts[model_index]
                
                endpoint = (
                    f"https://{self.location}-aiplatform.googleapis.com/v1/"
                    f"projects/{self.project_id}/locations/{self.location}/"
                    f"publishers/google/models/{model_name}:fetchPredictOperation"
                )
                
                payload = {
                    "operationName": operation_name
                }
                
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                }
                
                session = requests.Session()
                session.trust_env = False
                response = session.post(endpoint, json=payload, headers=headers, timeout=40)
                
                if response.status_code != 200:
                    return None
                
                response.raise_for_status()
                return response.json()
            
            return None
            
        except Exception as e:
            return None

    def wait_for_video(self, operation_name, max_wait_time=1200, check_interval=15):
        """Wait for video generation to complete"""
        start_time = time.time()
        last_log_time = start_time
        consecutive_failures = 0
        max_consecutive_failures = 10  # Ko'proq xatolarga ruxsat
        
        logger.info(f"⏳ Waiting for video completion...")
        
        while time.time() - start_time < max_wait_time:
            current_time = time.time()
            
            try:
                status = self.get_operation_status(operation_name)
            except Exception as e:
                logger.warning(f"⚠️ Status check error (will retry): {e}")
                consecutive_failures += 1
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"❌ Too many consecutive failures")
                    return None
                time.sleep(check_interval * 2)
                continue
            
            if not status:
                consecutive_failures += 1
                logger.warning(f"⚠️ No status received ({consecutive_failures}/{max_consecutive_failures})")
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"❌ Too many consecutive failures")
                    return None
                time.sleep(check_interval * 2)
                continue
            
            consecutive_failures = 0
            
            if status.get('done'):
                if 'error' in status:
                    error_info = status['error']
                    error_message = error_info.get('message', 'Unknown error')
                    logger.error(f"Operation failed: {error_message}")
                    return None
                
                if 'response' in status:
                    elapsed_time = int(time.time() - start_time)
                    logger.info(f"🎉 Video completed in {elapsed_time} seconds!")
                    return status['response']
                
                return None
            
            if current_time - last_log_time > 30:
                elapsed_time = int(current_time - start_time)
                progress_minutes = elapsed_time // 60
                logger.info(f"🔄 Generating... ({progress_minutes}m {elapsed_time % 60}s)")
                last_log_time = current_time
            
            time.sleep(check_interval)
        
        logger.error(f"⏱️ Timeout reached after {max_wait_time} seconds")
        return None


# Initialize Veo generator
veo_generator = GoogleVeoVideoGenerator(
    GOOGLE_PROJECT_ID,
    GOOGLE_LOCATION,
    GOOGLE_SERVICE_ACCOUNT_FILE
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /start command - ASOSIY MENYU"""
    user = update.effective_user
    
    # Foydalanuvchini bazaga qo'shish
    user_db.add_user(user.id, user.username, user.first_name)
    
    # Admin yoki oddiy foydalanuvchi
    is_admin = user.id in ADMIN_IDS
    admin_badge = " 👑" if is_admin else ""
    
    welcome_message = (
        f"╔══════════════════════╗\n"
        f"║ 🎬 **Jonlantir AI** {admin_badge} ║\n"
        f"╚══════════════════════╝\n\n"
        
        f"👋 Salom, **{user.first_name}**!\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **ASOSIY MENYU**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "🎬 **Video Yaratish** — 2 usulda video\n"
        "✍️ **Matn → Rasm** — Matndan rasm\n"
        "🎨 **Rasmni O'zgartir** — AI editing\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    # ASOSIY MENYU TUGMALARI
    keyboard = [
        [
            InlineKeyboardButton("🎬 Video Yaratish", callback_data="menu_video_creation")
        ],
        [
            InlineKeyboardButton("✍️ Matn → Rasm", callback_data="menu_text_to_image"),
            InlineKeyboardButton("🎨 Rasmni O'zgartir", callback_data="menu_edit_image")
        ],
        [
            InlineKeyboardButton("🎁 Mukofotlar", callback_data="loyalty_menu"),
            InlineKeyboardButton("📊 Statistika", callback_data="my_stats_button")
        ],
        [
            InlineKeyboardButton("ℹ️ Yordam", callback_data="help_menu")
        ]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)
    


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for photo messages - PARALLEL PROCESSING"""
    user = update.effective_user
    photo = update.message.photo[-1]
    
    logger.info(f"🎬 START: User {user.id} ({user.first_name}) ishni boshladi")
    
    # Foydalanuvchini bazaga qo'shish
    user_db.add_user(user.id, user.username, user.first_name)
    
    # Check if waiting for photo for editing or video
    waiting_for = context.user_data.get('waiting_for')
    
    # MATN ORQALI VIDEO MODE
    if waiting_for == 'photo_for_text_video':
        try:
            file = await context.bot.get_file(photo.file_id)
            image_url = file.file_path
            
            session = requests.Session()
            session.trust_env = False
            response = session.get(image_url, timeout=20)
            response.raise_for_status()
            image_bytes = response.content
            
            # Save image for video creation
            context.user_data['video_image_bytes'] = image_bytes
            context.user_data['waiting_for'] = 'text_for_video'
            
            await update.message.reply_text(
                "✅ **Rasm qabul qilindi!**\n\n"
                "📝 Endi **video tavsifini** yozing:\n\n"
                "🎬 **Video qanday bo'lishi kerak?**\n\n"
                "💡 **Yaxshi misollar:**\n"
                "• _\"Make the person smile warmly, wave hello, \"_\n"
                "  _\"then say: 'Salom, qalaysizlar!'\"_\n\n"
                "• _\"Start surprised with wide eyes, then laugh \"_\n"
                "  _\"and say something funny in Uzbek\"_\n\n"
                "• _\"Look emotional, speak softly about missing \"_\n"
                "  _\"someone, gentle expressions\"_\n\n"
                "📝 **Nima kiriting:**\n"
                "• Qanday harakat (smile, wave, nod)\n"
                "• Qanday kayfiyat (happy, sad, funny)\n"
                "• Nima deyishi kerak (O'zbek tilida)\n"
                "• Qanday ifoda (expressions)\n\n"
                "💬 **Til:** Inglizchada yozing (AI yaxshiroq tushunadi)\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            logger.info(f"✅ Image saved for text-based video - user {user.id}")
            return
        except Exception as e:
            logger.error(f"Image save error for user {user.id}: {e}")
            await update.message.reply_text(
                "❌ **Xatolik**\n\n"
                "Rasmni qayta yuboring.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            return
    
    # TASODIFIY VIDEO MODE
    if waiting_for == 'photo_for_random_video':
        # Use existing video creation logic with random prompt
        logger.info(f"🎲 Random video mode - user {user.id}")
        # We'll process this like normal video but with random prompt
        # Fall through to the normal video creation below
        # but mark it as random mode
        context.user_data['random_video_mode'] = True
    
    if waiting_for == 'photo_for_edit':
        # IMAGE EDITING MODE - Advanced AI with preservation rules
        try:
            file = await context.bot.get_file(photo.file_id)
            image_url = file.file_path
            
            session = requests.Session()
            session.trust_env = False
            response = session.get(image_url, timeout=20)
            response.raise_for_status()
            image_bytes = response.content
            
            # Save image for editing
            context.user_data['edit_image_bytes'] = image_bytes
            context.user_data['waiting_for'] = 'edit_instruction'
            
            await update.message.reply_text(
                "✅ **Rasm qabul qilindi!**\n\n"
                "📝 Endi **o'zgartirish matnini** yozing:\n\n"
                "🛡️ **Avtomatik saqlanadi:**\n"
                "• Yuz va identifikatsiya\n"
                "• Tabiiy proporsiyalar\n"
                "• Yorug'lik va soyalar\n"
                "• Asl kompozitsiya\n\n"
                "🎨 **TO'G'RI misollar:**\n"
                "• _\"Add sunset background\"_\n"
                "• _\"Change to cartoon style\"_\n"
                "• _\"Add flowers in the foreground\"_\n"
                "• _\"Remove background objects\"_\n"
                "• _\"Change sky to starry night\"_\n\n"
                "💡 **Qoidalar:**\n"
                "• Inglizchada yozing\n"
                "• Aniq va qisqa\n"
                "• Bitta o'zgarish\n"
                "• Oddiy so'zlar\n\n"
                "⚠️ **NOTO'G'RI:**\n"
                "• Uzun va murakkab\n"
                "• Ko'p narsani bir vaqtda\n"
                "• Noaniq so'rovlar\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            logger.info(f"✅ Image saved for editing - user {user.id}")
            return
        except Exception as e:
            logger.error(f"Image save error for user {user.id}: {e}")
            await update.message.reply_text(
                "❌ **Xatolik**\n\n"
                "Rasmni qayta yuboring.\n\n"
                "📝 **Talablar:**\n"
                "• JPEG/PNG format\n"
                "• Max 10MB\n"
                "• Aniq va sifatli\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            return
    
    # IMAGE TO VIDEO MODE (default)
    # CHEKLOV TEKSHIRUVI (Admin uchun cheklov yo'q)
    can_create, time_left = user_db.can_create_video(user.id, consume_loyalty_skip=True)
    
    logger.info(f"✅ PARALLEL: User {user.id} can_create={can_create}, parallel processing active")
    
    if not can_create:
        hours = int(time_left // 3600)
        minutes = int((time_left % 3600) // 60)
        
        await update.message.reply_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ ⏳ **KUTISH VAQTI** ⏳ ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"⚠️ Siz allaqachon video yaratgansiz!\n\n"
            f"🕐 **Keyingi video:** {hours} soat {minutes} daqiqadan keyin\n\n"
            f"💎 **Cheklovsiz video uchun:**\n"
            f"Admin bilan bog'laning\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🤖 @Jonlantir_Ai_bot\n"
            f"━━━━━━━━━━━━━━━━━━",
            parse_mode='Markdown'
        )
        return
    
    # CHIROYLI LOADING ANIMATSIYA - BOSHLASH
    wait_msg = await update.message.reply_text(
        "┏━━━━━━━━━━━━━━━━━━━┓\n"
        "┃ 📸 **RASM QABUL QILINDI** ┃\n"
        "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
        "🔄 **Jarayon boshlandi...**\n\n"
        "▰▰▰▱▱▱▱▱▱▱ 30%\n\n"
        "⏳ *Iltimos, kuting...*",
        parse_mode='Markdown'
    )
    
    try:
        # Rasmni yuklash
        file = await context.bot.get_file(photo.file_id)
        image_url = file.file_path
        
        logger.info(f"📥 User {user.id} started video creation")
        
        # Rasmni yuklab olish
        session = requests.Session()
        session.trust_env = False
        response = session.get(image_url, timeout=20)
        response.raise_for_status()
        image_bytes = response.content
        
        # Rasmni CHUQUR tahlil qilish
        analyzer = ImageAnalyzer(GOOGLE_SERVICE_ACCOUNT_FILE)
        analysis = analyzer.analyze_image(image_bytes)
        
        # DEBUG LOG
        if analysis:
            logger.info(f"🔍 Analysis result: faces={analysis.get('face_count')}, labels={analysis.get('labels', [])[:5]}, is_old={analysis.get('is_old_photo')}")
        else:
            logger.warning(f"⚠️ Analysis failed - using default prompt")
        
        # LOADING ANIMATSIYA - TAHLIL
        await wait_msg.edit_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ 🔍 **AI TAHLIL QILMOQDA** ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            "🤖 *Rasm o'rganilmoqda...*\n\n"
            "▰▰▰▰▰▰▱▱▱▱ 60%\n\n"
            "✨ *Bir daqiqa...*",
            parse_mode='Markdown'
        )
        
        # AGAR ESKI/XIRA RASM BO'LSA - YAXSHILASH
        if analysis and analysis.get('is_old_photo'):
            await wait_msg.edit_text(
                "┏━━━━━━━━━━━━━━━━━━━┓\n"
                "┃ 🎨 **RASM YAXSHILANMOQDA** ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                "✨ *Eski rasm aniqlandi*\n"
                "🌈 *Rangli qilinmoqda...*\n\n"
                "▰▰▰▰▰▰▰▱▱▱ 70%\n\n"
                "⏳ *Iltimos, kuting...*",
                parse_mode='Markdown'
            )
            
            # Rasmni yaxshilash - HOLAT ASOSIDA
            image_bytes = analyzer.enhance_old_photo(image_bytes, analysis)
            logger.info(f"✨ Old photo enhanced for user {user.id} - HOLAT ASOSIDA")
        
        # CHECK FOR RANDOM VIDEO MODE (from new menu)
        random_video_mode = context.user_data.get('random_video_mode', False)
        loyalty_prompts = user_db.get_loyalty_prompts(user.id)
        selected_style = None
        used_loyalty_prompt = False
        
        def try_loyalty_prompt(probability: float):
            nonlocal selected_style, used_loyalty_prompt
            if selected_style is None and loyalty_prompts and random.random() < probability:
                selected_style = random.choice(loyalty_prompts)
                used_loyalty_prompt = True
                logger.info(f"💎 LOYALTY PROMPT: User {user.id} - {selected_style['name']}")
        
        if random_video_mode:
            try_loyalty_prompt(0.45)
            if selected_style is None:
                # TASODIFIY VIDEO MODE - Random prompt tanlash
                selected_style = get_random_prompt()
                logger.info(f"🎲 TASODIFIY VIDEO MODE: User {user.id} - {selected_style['name']}")
            # Clear random_video_mode flag
            context.user_data.pop('random_video_mode', None)
        else:
            # TEMPLATE VA KATEGORIYA TANLASH (existing logic)
            selected_template = context.user_data.get('selected_template', 'auto')
            selected_category = context.user_data.get('selected_category', None)
            
            if selected_category:
                try_loyalty_prompt(0.35)
                if selected_style is None:
                    # KATEGORIYA MODE - 5ta random prompt tanlash
                    category_prompts = get_random_category_prompts(selected_category, 5)
                    if category_prompts:
                        selected_style = random.choice(category_prompts)
                        logger.info(f"🎭 CATEGORY MODE: User {user.id} - Category: {selected_category}, Prompt: {selected_style['name']}")
                    else:
                        selected_style = analyzer.generate_uzbek_prompt(analysis)
            elif selected_template == 'comedy':
                try_loyalty_prompt(0.5)
                if selected_style is None:
                    # Random prompt tanlash - YANGI COMEDY + ESKI PROMPTS
                    selected_style = get_random_prompt()
                    logger.info(f"🎭 COMEDY/RANDOM MODE: User {user.id} - {selected_style['name']}")
            else:
                try_loyalty_prompt(0.25)
                if selected_style is None:
                    # Rasmga mos o'zbek tilida DINAMIK prompt yaratish
                    selected_style = analyzer.generate_uzbek_prompt(analysis)
        
        if selected_style is None:
            selected_style = analyzer.generate_uzbek_prompt(analysis)
        
        loyalty_hint = "\n💎 VIP prompt faollashdi!" if used_loyalty_prompt else ""
        
        # DEBUG LOG
        logger.info(f"🎭 Selected scenario: {selected_style['name']}")
        logger.info(f"🗣️ Uzbek text: {selected_style.get('uzbek_text', 'N/A')[:50]}")
        
        # LOADING ANIMATSIYA - TAYYOR
        await wait_msg.edit_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ ✅ **TAHLIL TUGADI** ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"🎭 **{selected_style['name']}**{loyalty_hint}\n"
            f"🗣️ _{selected_style.get('uzbek_text', '')[:45]}_...\n\n"
            "▰▰▰▰▰▰▰▰▱▱ 80%\n\n"
            "🎬 *Video yaratish boshlandi...*",
            parse_mode='Markdown'
        )
        
        logger.info(f"🎭 SCENARIO: User {user.id} - {selected_style['name']}")
        logger.info(f"🔄 PARALLEL: User {user.id} video yaratish boshlandi (parallel mode)")
        
        # Videoni yaratish (yaxshilangan rasm bilan) - PARALLEL
        result = veo_generator.create_video_from_image(
            image_url=None,  # URL o'rniga bytes ishlatamiz
            prompt=selected_style['prompt'],
            image_bytes=image_bytes  # Yaxshilangan rasm
        )
        
        logger.info(f"✅ API RESPONSE: User {user.id} - operation started")
        
        if not result or 'name' not in result:
            await wait_msg.edit_text(
                "❌ **Xatolik**\n\n"
                "Boshqa rasm yuboring\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            return
        
        operation_name = result['name']
        
        await wait_msg.edit_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ 🎬 **VIDEO YARATILMOQDA** ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            "🎨 *Sahna yaratilmoqda...*\n"
            "🎵 *Audio qo'shilmoqda...*\n\n"
            "▰▰▰▰▰▰▰▰▰▱ 90%\n\n"
            "⏳ *2-15 daqiqa kutish...*",
            parse_mode='Markdown'
        )
        
        # Wait for video with progress updates
        start_time = time.time()
        last_update_time = start_time
        video_data = None
        
        async def wait_with_updates():
            nonlocal video_data, last_update_time
            while True:
                # Check if video is ready
                if video_data is None:
                    # Check status every 2 seconds
                    await asyncio.sleep(2)
                    elapsed = int(time.time() - start_time)
                    
                    # Update message every 30 seconds
                    if time.time() - last_update_time > 30:
                        minutes = elapsed // 60
                        seconds = elapsed % 60
                        
                        # Progress foizini hisoblash (taxminiy)
                        progress_percent = min(90 + (elapsed // 60), 99)
                        progress_bar = "▰" * (progress_percent // 10) + "▱" * (10 - progress_percent // 10)
                        
                        # Animatsion emoji
                        animation_frames = ["🎬", "🎨", "🎵", "✨", "🎭", "💫"]
                        emoji = animation_frames[(elapsed // 30) % len(animation_frames)]
                        
                        await wait_msg.edit_text(
                            "┏━━━━━━━━━━━━━━━━━━━┓\n"
                            f"┃ {emoji} **VIDEO TAYYORLANMOQDA** {emoji} ┃\n"
                            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                            f"⏱️ *O'tgan vaqt:* **{minutes}m {seconds}s**\n"
                            f"📊 *Progress:* {progress_bar} {progress_percent}%\n\n"
                            "🎨 *AI ishlamoqda...*\n"
                            "🎵 *Audio qo'shilmoqda...*\n"
                            "🎬 *Sahna yaratilmoqda...*\n\n"
                            "⏳ *Iltimos, sabr qiling...*",
                            parse_mode='Markdown'
                        )
                        last_update_time = time.time()
                else:
                    break
        
        # Start waiting in background
        update_task = asyncio.create_task(wait_with_updates())
        
        logger.info(f"⏳ WAITING: User {user.id} - kutish boshlandi (parallel executor)")
        
        # PARALLEL PROCESSING - Default executor parallel ishlaydi
        # Python avtomatik ravishda har bir foydalanuvchi uchun alohida thread yaratadi
        # None = Default ThreadPoolExecutor (CPU count * 5 threads)
        
        # Wait for video (blocking call in thread) - PARALLEL har bir user uchun
        video_data = await asyncio.get_event_loop().run_in_executor(
            None,  # Default executor - parallel ishlaydi
            veo_generator.wait_for_video, 
            operation_name
        )
        
        logger.info(f"🎉 COMPLETE: User {user.id} - video tayyor!")
        
        # Cancel update task
        update_task.cancel()
        try:
            await update_task
        except asyncio.CancelledError:
            pass
        
        if video_data and 'videos' in video_data and len(video_data['videos']) > 0:
            video_info = video_data['videos'][0]
            
            if 'bytesBase64Encoded' in video_info:
                # LOADING ANIMATSIYA - TUGADI
                await wait_msg.edit_text(
                    "┏━━━━━━━━━━━━━━━━━━━┓\n"
                    "┃ 🎉 **VIDEO TAYYOR!** 🎉 ┃\n"
                    "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                    "✨ *Video tayyorlandi*\n\n"
                    "▰▰▰▰▰▰▰▰▰▰ 100%\n\n"
                    "📤 *Yuborilmoqda...*",
                    parse_mode='Markdown'
                )
                
                video_bytes = base64.b64decode(video_info['bytesBase64Encoded'])
                temp_video_path = f"temp_video_{user.id}_{int(time.time())}.mp4"
                
                with open(temp_video_path, 'wb') as f:
                    f.write(video_bytes)
                
                # Video yaratishni qayd qilish
                loyalty_update = user_db.record_video_creation(user.id)
                
                # Keyingi video uchun vaqtni hisoblash
                is_admin = user.id in ADMIN_IDS
                next_video_time = ""
                
                if not is_admin:
                    next_video_time = f"\n\n⏰ **Keyingi video:** {VIDEO_COOLDOWN_HOURS} soatdan keyin"
                
                loyalty_lines = ""
                if loyalty_update:
                    loyalty_lines = (
                        f"\n💎 {loyalty_update.get('tier_emoji', '')} {loyalty_update.get('tier', '')} — "
                        f"+{loyalty_update.get('points_added', 0)} bal"
                        f"\n📈 Jami: {loyalty_update.get('total_points', 0)} bal"
                    )
                
                # CHIROYLI CAPTION BOT LINKI BILAN
                caption = (
                    "╔═══════════════════╗\n"
                    "║ 🎬 **VIDEO TAYYOR!** ║\n"
                    "╚═══════════════════╝\n\n"
                    "✅ *Muvaffaqiyatli yaratildi*"
                    f"{next_video_time}{loyalty_lines}\n\n"
                    "📸 *Boshqa rasm yuboring!*\n\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🤖 @Jonlantir_Ai_bot\n"
                    "━━━━━━━━━━━━━━━━━━"
                )
                
                with open(temp_video_path, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=user.id,
                        video=video_file,
                        caption=caption,
                        supports_streaming=True,
                        parse_mode='Markdown'
                    )
                
                # Tozalash
                os.remove(temp_video_path)
                await wait_msg.delete()
                
                logger.info(f"✅ Video sent to user {user.id} - Next video in {VIDEO_COOLDOWN_HOURS} hours")
                return
        
        # Agar video yaratish muvaffaqiyatsiz tugasa
        await wait_msg.edit_text(
            "❌ **Xatolik**\n\n"
            "Boshqa rasm yuboring\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🤖 @Jonlantir_Ai_bot\n"
            "━━━━━━━━━━━━━━━━━━",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"❌ Error for user {user.id}: {e}")
        await wait_msg.edit_text(
            "❌ **Xatolik**\n\n"
            "Boshqa rasm yuboring\n\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🤖 @Jonlantir_Ai_bot\n"
            "━━━━━━━━━━━━━━━━━━",
            parse_mode='Markdown'
        )


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel - PRODUCTION READY - Fully tested and working"""
    user = update.effective_user
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    # Authorization check
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ Ruxsat yo'q!\n\n"
            "Bu buyruq faqat adminlar uchun."
        )
        return
    
    try:
        # Reload database from file (to get latest data)
        user_db.data = user_db.load_db()
        
        # Get statistics
        stats = user_db.get_all_stats()
        if not stats:
            stats = {'total_users': 0, 'total_videos': 0, 'active_today': 0}
        
        # Get top 10 users by videos created
        top_users = sorted(
            user_db.data.items(),
            key=lambda x: x[1].get('videos_created', 0) if isinstance(x[1], dict) else 0,
            reverse=True
        )[:10]
        
        # Build admin text - PLAIN TEXT (no formatting issues)
        admin_text = (
            "┏━━━━━━━━━━━━━━━━━┓\n"
            "┃ 👑 ADMIN 👑 ┃\n"
            "┗━━━━━━━━━━━━━━━━━┛\n\n"
            
            f"👥 Userlar: {stats.get('total_users', 0)}\n"
            f"🎬 Videolar: {stats.get('total_videos', 0)}\n"
            f"✅ Bugun: {stats.get('active_today', 0)}\n\n"
            
            "🏆 TOP 10:\n"
        )
        
        # Add users to display - Fixed enumeration
        user_count = 0
        for user_id, user_data in top_users:
            if not isinstance(user_data, dict):
                continue
            
            user_count += 1
            username = user_data.get('username')
            first_name = str(user_data.get('first_name', 'Noma\'lum'))[:30]
            videos = user_data.get('videos_created', 0)
            
            # Display username or ID
            user_display = f"@{username}" if (username and isinstance(username, str) and username.strip()) else f"ID: {str(user_id)[:8]}"
            
            admin_text += f"{user_count}. {first_name} ({user_display}) - {videos} video\n"
        
        admin_text += (
            "\n━━━━━━━━━━━━━━━━━━\n"
            "🤖 @Jonlantir_Ai_bot\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        
        # Truncate if message too long
        if len(admin_text) > 4000:
            admin_text = admin_text[:3900] + "\n\n... va yana ko'proq"
        
        # Create buttons
        keyboard = [
            [
                InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users_list"),
                InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast")
            ],
            [
                InlineKeyboardButton("📊 Stats", callback_data="admin_detailed_stats")
            ]
        ]
        
        # Send message
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(admin_text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Admin panel error: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Admin Panel Xatosi\n\n"
            "Vaqtinchalik muammo. Iltimos:\n"
            "1. Qayta /admin bosing\n"
            "2. Bot owner bilan bog'lanish"
        )
        return


# ==========================================
# 👥 ADMIN USERS LIST - FOYDALANUVCHILAR ROYHATI
# ==========================================
async def admin_users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Barcha foydalanuvchilar ro'yxati - pagination bilan"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Ruxsat yo'q!")
        return
    
    # Limit: 20 ta user (Telegram message limit uchun)
    MAX_USERS = 20
    users_list = ""
    total_users = len(user_db.data)
    
    for i, (user_id, user_data) in enumerate(list(user_db.data.items())[:MAX_USERS], 1):
        username = user_data.get('username')
        first_name = user_data.get('first_name', 'Noma\'lum')
        videos = user_data.get('videos_created', 0)
        
        if username:
            users_list += f"{i}. {first_name} (@{username}) - {videos} video\n"
        else:
            users_list += f"{i}. {first_name} (ID: {user_id[:8]}...) - {videos} video\n"
    
    # Agar ko'proq user bo'lsa
    if total_users > MAX_USERS:
        users_list += f"\n... va yana {total_users - MAX_USERS} ta user"
    
    keyboard = [
        [InlineKeyboardButton("◀️ Orqaga", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(
        text=f"👥 <b>BARCHA FOYDALANUVCHILAR ({total_users} TA)</b>\n\n{users_list}",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# 📨 BROADCAST - BARCHA USERLARGA XABAR
# ==========================================
async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast xabarini yuborish"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Ruxsat yo'q!")
        return
    
    await query.edit_message_text(
        text="📨 <b>BROADCAST XABARI</b>\n\n"
             "Xabar matni yozing.\n"
             "U barcha foydalanuvchilarga yuboriladi!\n\n"
             "<b>Misol:</b> 'Yangi funktsiya qo'shildi!'",
        parse_mode='HTML'
    )
    
    context.user_data['waiting_for_broadcast'] = True


# ==========================================
# 📊 DETAILED STATS - BATAFSIL STATISTIKA
# ==========================================
async def admin_detailed_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Batafsil statistika"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Ruxsat yo'q!")
        return
    
    stats = user_db.get_all_stats()
    
    detailed_stats = (
        f"📊 <b>BATAFSIL STATISTIKA</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['total_users']}</b>\n"
        f"🎬 Jami videolar: <b>{stats['total_videos']}</b>\n"
        f"✅ Bugun faol: <b>{stats['active_today']}</b>\n\n"
        f"📈 O'rtacha: <b>{stats['total_videos'] // max(stats['total_users'], 1)}</b> video/user"
    )
    
    keyboard = [
        [InlineKeyboardButton("◀️ Orqaga", callback_data="admin_back")]
    ]
    
    await query.edit_message_text(detailed_stats, parse_mode='HTML', reply_markup=InlineKeyboardMarkup(keyboard))


async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel'ga qaytish - CALLBACK VERSION"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Ruxsat yo'q!")
        return
    
    # Reload database
    user_db.data = user_db.load_db()
    
    # Statistikani olish
    stats = user_db.get_all_stats()
    
    # Eng faol foydalanuvchilar
    top_users = sorted(
        user_db.data.items(),
        key=lambda x: x[1].get('videos_created', 0) if isinstance(x[1], dict) else 0,
        reverse=True
    )[:10]
    
    admin_text = (
        "┏━━━━━━━━━━━━━━━━━┓\n"
        "┃ 👑 ADMIN 👑 ┃\n"
        "┗━━━━━━━━━━━━━━━━━┛\n\n"
        
        f"👥 Userlar: {stats['total_users']}\n"
        f"🎬 Videolar: {stats['total_videos']}\n"
        f"✅ Bugun: {stats['active_today']}\n\n"
        
        "🏆 TOP 10:\n"
    )
    
    for i, (user_id, user_data) in enumerate(top_users, 1):
        if not isinstance(user_data, dict):
            continue
        username = user_data.get('username') or 'username_yoq'
        first_name = user_data.get('first_name', 'Noma\'lum')
        videos = user_data.get('videos_created', 0)
        
        if username and username != 'username_yoq':
            admin_text += f"{i}. {first_name} (@{username}) - {videos} video\n"
        else:
            admin_text += f"{i}. {first_name} (ID: {user_id}) - {videos} video\n"
    
    admin_text += (
        "\n━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    # ADMIN MENYU TUGMALARI
    keyboard = [
        [
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users_list"),
            InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_detailed_stats")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(admin_text, reply_markup=reply_markup)


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin panel - CALLBACK HANDLER"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Ruxsat yo'q!")
        return
    
    # Reload database
    user_db.data = user_db.load_db()
    
    # Statistikani olish
    stats = user_db.get_all_stats()
    
    # Eng faol foydalanuvchilar
    top_users = sorted(
        user_db.data.items(),
        key=lambda x: x[1].get('videos_created', 0) if isinstance(x[1], dict) else 0,
        reverse=True
    )[:10]
    
    admin_text = (
        "┏━━━━━━━━━━━━━━━━━┓\n"
        "┃ 👑 ADMIN 👑 ┃\n"
        "┗━━━━━━━━━━━━━━━━━┛\n\n"
        
        f"👥 Userlar: {stats['total_users']}\n"
        f"🎬 Videolar: {stats['total_videos']}\n"
        f"✅ Bugun: {stats['active_today']}\n\n"
        
        "🏆 TOP 10:\n"
    )
    
    for i, (user_id, user_data) in enumerate(top_users, 1):
        if not isinstance(user_data, dict):
            continue
        username = user_data.get('username') or 'username_yoq'
        first_name = user_data.get('first_name', 'Noma\'lum')
        videos = user_data.get('videos_created', 0)
        
        if username and username != 'username_yoq':
            admin_text += f"{i}. {first_name} (@{username}) - {videos} video\n"
        else:
            admin_text += f"{i}. {first_name} (ID: {user_id}) - {videos} video\n"
    
    admin_text += (
        "\n━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    # ADMIN MENYU TUGMALARI
    keyboard = [
        [
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users_list"),
            InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_detailed_stats")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(admin_text, reply_markup=reply_markup)
    """Admin panel'ga qaytish"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    if user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Ruxsat yo'q!")
        return
    
    # Statistikani olish
    stats = user_db.get_all_stats()
    
    # Eng faol foydalanuvchilar
    top_users = sorted(
        user_db.data.items(),
        key=lambda x: x[1].get('videos_created', 0),
        reverse=True
    )[:10]
    
    admin_text = (
        "┏━━━━━━━━━━━━━━━━━┓\n"
        "┃ 👑 **ADMIN** 👑 ┃\n"
        "┗━━━━━━━━━━━━━━━━━┛\n\n"
        
        f"👥 Userlar: **{stats['total_users']}**\n"
        f"🎬 Videolar: **{stats['total_videos']}**\n"
        f"✅ Bugun: **{stats['active_today']}**\n\n"
        
        "🏆 **TOP 10:**\n"
    )
    
    for i, (user_id, user_data) in enumerate(top_users, 1):
        username = user_data.get('username') or 'username_yoq'
        first_name = user_data.get('first_name', 'Noma\'lum')
        videos = user_data.get('videos_created', 0)
        
        if username and username != 'username_yoq':
            admin_text += f"{i}. {first_name} (@{username}) - {videos} video\n"
        else:
            admin_text += f"{i}. {first_name} (ID: {user_id}) - {videos} video\n"
    
    admin_text += (
        "\n━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    # ADMIN MENYU TUGMALARI
    keyboard = [
        [
            InlineKeyboardButton("👥 Foydalanuvchilar", callback_data="admin_users_list"),
            InlineKeyboardButton("📨 Broadcast", callback_data="admin_broadcast")
        ],
        [
            InlineKeyboardButton("📊 Stats", callback_data="admin_detailed_stats")
        ]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(admin_text, parse_mode='Markdown', reply_markup=reply_markup)


async def handle_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Broadcast xabarini barcha userlarga yuborish"""
    user = update.effective_user
    
    # Tekshirish 1: Admin mi?
    if user.id not in ADMIN_IDS:
        return
    
    # Tekshirish 2: broadcast mode'da mi?
    if not context.user_data.get('waiting_for_broadcast'):
        return
    
    message_text = update.message.text
    
    # Loading message
    wait_msg = await update.message.reply_text(
        "📨 <b>XABAR YUBORILMOQDA...</b>\n\n"
        "⏳ Iltimos, kuting...",
        parse_mode='HTML'
    )
    
    # Barcha userlarga xabar yuborish
    success_count = 0
    error_count = 0
    blocked_count = 0
    
    total_users = len(user_db.data)
    
    for user_id in list(user_db.data.keys()):
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=f"📢 <b>ADMIN XABARI</b>\n\n{message_text}",
                parse_mode='HTML'
            )
            success_count += 1
        except Exception as e:
            error_str = str(e)
            if "blocked" in error_str.lower() or "403" in error_str:
                blocked_count += 1
            else:
                error_count += 1
            logger.error(f"Broadcast error for user {user_id}: {e}")
    
    # Admin'ga result
    result_text = (
        f"✅ <b>BROADCAST TUGALLANDI!</b>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"✅ Muvaffaqiyatli: <b>{success_count}</b>\n"
        f"❌ Xato: <b>{error_count}</b>\n"
        f"🚫 Blok qilgan: <b>{blocked_count}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 Jami: <b>{total_users}</b>"
    )
    
    await wait_msg.edit_text(result_text, parse_mode='HTML')
    context.user_data['waiting_for_broadcast'] = False
    
    logger.info(f"✅ BROADCAST: Success={success_count}, Error={error_count}, Blocked={blocked_count}")


async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi o'z statistikasini ko'radi"""
    user = update.effective_user
    
    user_db.add_user(user.id, user.username, user.first_name)
    stats = user_db.get_user_stats(user.id)
    
    if not stats:
        await update.message.reply_text("Ma'lumot topilmadi.")
        return
    
    loyalty_profile = user_db.get_loyalty_profile(user.id)
    
    loyalty_profile = user_db.get_loyalty_profile(user.id)
    
    # Keyingi video vaqti
    can_create, time_left = user_db.can_create_video(user.id)
    
    is_admin = user.id in ADMIN_IDS
    status = "👑 **ADMIN** (Cheklovsiz)" if is_admin else "👤 **Oddiy foydalanuvchi**"
    
    next_video = ""
    if not can_create and not is_admin:
        hours = int(time_left // 3600)
        minutes = int((time_left % 3600) // 60)
        next_video = f"\n⏰ **Keyingi video:** {hours} soat {minutes} daqiqadan keyin"
    elif is_admin:
        next_video = "\n✅ **Hozir video yarata olasiz!** (Admin)"
    else:
        next_video = "\n✅ **Hozir video yarata olasiz!**"
    
    loyalty_lines = (
        f"💎 {loyalty_profile.get('tier_emoji', '')} {loyalty_profile.get('tier', '')}\n"
        f"   Ballar: **{loyalty_profile.get('points', 0)}**\n"
        f"   Keyingi daraja: {loyalty_profile.get('points_to_next', 0)} bal\n"
        f"   🎁 Promo tayyor: {loyalty_profile.get('available_promotions', 0)}\n"
    )
    if loyalty_profile.get('cooldown_tokens', 0) > 0:
        loyalty_lines += f"   ⏭️ Bonus token: {loyalty_profile.get('cooldown_tokens')} ta\n"
    
    stats_text = (
        "┏━━━━━━━━━━━━━━━━━┓\n"
        "┃ 📊 **STATISTIKA** ┃\n"
        "┗━━━━━━━━━━━━━━━━━┛\n\n"
        
        f"👤 {stats['first_name']}\n"
        f"🏅 {status}\n\n"
        f"{loyalty_lines}\n"
        
        f"🎬 Videolar: **{stats['videos_created']}**\n"
        f"{next_video}\n\n"
        
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')


# ==========================================
# 🎨 SHABLONLAR MENYU - TEMPLATES MENU
# ==========================================
async def templates_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shablonlar menyu - Sevgi, Bayram, Oila, Xotira, Trend, COMEDY"""
    query = update.callback_query
    await query.answer()
    
    template_keyboards = [
        [
            InlineKeyboardButton("❤️ Sevgi", callback_data="template_love"),
            InlineKeyboardButton("🎉 Bayram", callback_data="template_holiday")
        ],
        [
            InlineKeyboardButton("👨‍👩‍👧 Oila", callback_data="template_family"),
            InlineKeyboardButton("💫 Xotira", callback_data="template_memory")
        ],
        [
            InlineKeyboardButton("🔥 Trend", callback_data="template_trend"),
            InlineKeyboardButton("🎭 COMEDY", callback_data="template_comedy")
        ],
        [
            InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_menu")
        ]
    ]
    
    template_markup = InlineKeyboardMarkup(template_keyboards)
    
    await query.edit_message_text(
        text="🎨 <b>SHABLONLARNI TANLANG</b>\n\n"
             "Qaysi mavzu haqida video yaratmoqchi?",
        reply_markup=template_markup,
        parse_mode="HTML"
    )


# ==========================================
# 💖 TEMPLATE CALLBACKS
# ==========================================
async def template_love(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sevgi shabloni"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_template'] = 'love'
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="wait_for_photo")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="templates_menu")]
    ]
    
    await query.edit_message_text(
        text="❤️ <b>SEVGI SHABLONI</b>\n\n"
             "Bu shablonda rasmingiz sevgi bilan jonlanadi:\n"
             "• Yumrak nigohlar\n"
             "• Iliq tabassum\n"
             "• Qalb yubiydigan mavzular\n\n"
             "Rasm yuboring:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def template_holiday(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Bayram shabloni"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_template'] = 'holiday'
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="wait_for_photo")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="templates_menu")]
    ]
    
    await query.edit_message_text(
        text="🎉 <b>BAYRAM SHABLONI</b>\n\n"
             "Bu shablonda rasmingiz bayramga tolangan videoga aylandi:\n"
             "• Quvonch bilan kulgi\n"
             "• Bayramchil hifasi\n"
             "• O'zbek bayram mavzulari\n\n"
             "Rasm yuboring:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def template_family(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Oila shabloni"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_template'] = 'family'
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="wait_for_photo")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="templates_menu")]
    ]
    
    await query.edit_message_text(
        text="👨‍👩‍👧 <b>OILA SHABLONI</b>\n\n"
             "Bu shablonda rasmingiz oilaviy muhabbat bilan jonlanadi:\n"
             "• Oilaning kuchli bog'lanishi\n"
             "• Bir-birlari bilan qo'llab-quvvatlash\n"
             "• Oilaviy xotiralar\n\n"
             "Rasm yuboring:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def template_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xotira shabloni"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_template'] = 'memory'
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="wait_for_photo")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="templates_menu")]
    ]
    
    await query.edit_message_text(
        text="💫 <b>XOTIRA SHABLONI</b>\n\n"
             "Bu shablonda rasmingiz o'tgan xotiralar bilan jonlanadi:\n"
             "• O'tgan kunlarni eslash\n"
             "• Sog'inch bilan tabassum\n"
             "• Samimiy hissiyotlar\n\n"
             "Rasm yuboring:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def template_trend(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Trend shabloni"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_template'] = 'trend'
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="wait_for_photo")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="templates_menu")]
    ]
    
    await query.edit_message_text(
        text="🔥 <b>TREND SHABLONI</b>\n\n"
             "Bu shablonda rasmingiz trend mavzuda jonlanadi:\n"
             "• Zamonaviy video effektlari\n"
             "• Dinamik harakatlar\n"
             "• Sifatli ta'mir\n\n"
             "Rasm yuboring:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ==========================================
# 📁 KATEGORIYA MENYU - CATEGORY MENU
# ==========================================
async def category_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """📁 Kategoriya boyicha video"""
    query = update.callback_query
    await query.answer()
    
    # Kategoriya tugmalari
    keyboard = [
        [
            InlineKeyboardButton("😂 KULGILI", callback_data="cat_funny"),
            InlineKeyboardButton("👴 NOSTALGIK", callback_data="cat_nostalgic")
        ],
        [
            InlineKeyboardButton("🎉 BAYRAMONA", callback_data="cat_festive"),
            InlineKeyboardButton("😢 EMOTSIONAL", callback_data="cat_emotional")
        ],
        [
            InlineKeyboardButton("🔥 DRAMATIK", callback_data="cat_dramatic"),
            InlineKeyboardButton("🕰 RETRO", callback_data="cat_retro")
        ],
        [
            InlineKeyboardButton("❤️ SENTIMENTAL", callback_data="cat_sentimental"),
            InlineKeyboardButton("🥳 PARTY", callback_data="cat_party")
        ],
        [
            InlineKeyboardButton("😔 SOG'INCH", callback_data="cat_soft_sad"),
            InlineKeyboardButton("💥 KUCHLI", callback_data="cat_strong_dramatic")
        ],
        [
            InlineKeyboardButton("💼 BOSS", callback_data="cat_boss_confident")
        ],
        [
            InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_menu")
        ]
    ]
    
    await query.edit_message_text(
        text="📁 <b>KATEGORIYA BOYICHA VIDEO</b>\n\n"
             "🎬 <b>Kategoriyani Tanlang:</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# KATEGORIYA CALLBACKS
async def category_selected(update: Update, context: ContextTypes.DEFAULT_TYPE, category: str):
    """Kategoriya tanlash va rasm soroq"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_category'] = category
    
    # Kategoriya nomini olish
    category_names = {
        "funny": "😂 KULGILI",
        "nostalgic": "👴 NOSTALGIK",
        "festive": "🎉 BAYRAMONA",
        "emotional": "😢 EMOTSIONAL",
        "dramatic": "🔥 DRAMATIK",
        "retro": "🕰 RETRO",
        "sentimental": "❤️ SENTIMENTAL",
        "party": "🥳 PARTY",
        "soft_sad": "😔 SOG'INCH",
        "strong_dramatic": "💥 KUCHLI",
        "boss_confident": "💼 BOSS"
    }
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="cat_upload_photo")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="category_menu")]
    ]
    
    await query.edit_message_text(
        text=f"<b>{category_names.get(category, category)}</b>\n\n"
             "📸 <b>Rasm yuboringmi?</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# Category callback wrappers
async def cat_funny(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "funny")

async def cat_nostalgic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "nostalgic")

async def cat_festive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "festive")

async def cat_emotional(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "emotional")

async def cat_dramatic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "dramatic")

async def cat_retro(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "retro")

async def cat_sentimental(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "sentimental")

async def cat_party(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "party")

async def cat_soft_sad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "soft_sad")

async def cat_strong_dramatic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "strong_dramatic")

async def cat_boss_confident(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await category_selected(update, context, "boss_confident")

async def cat_upload_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Kategoriya bo'yicha rasm yuborishni soroq"""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            
            # State ni o'rnatish - rasm kutayotganimizni belgilash
            context.user_data['waiting_for_photo'] = True
            
            await query.edit_message_text(
                text="📸 <b>RASM YUBORINGMI?</b>\n\n"
                     "Pastdagi chat'ga rasmni yuboring,\n"
                     "AI 5ta random prompt ishlatib video yaratadi!\n\n"
                     "💡 <i>Yuqori sifatli rasm yuboring (JPG yoki PNG)</i>\n"
                     "⏱️ <i>Video 2-15 daqiqada tayyor bo'ladi</i>",
                parse_mode="HTML"
            )
            logger.info(f"📸 User {update.effective_user.id} - Kategoriya bo'yicha rasm yuborishni kutmoqda")
        else:
            await update.message.reply_text(
                text="📸 <b>RASM YUBORINGMI?</b>\n\n"
                     "Rasmni yuboring, AI 5ta random prompt ishlatib video yaratadi!\n\n"
                     "💡 <i>Yuqori sifatli rasm yuboring (JPG yoki PNG)</i>\n"
                     "⏱️ <i>Video 2-15 daqiqada tayyor bo'ladi</i>",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"❌ Error in cat_upload_photo: {e}")
        try:
            query = update.callback_query
            if query:
                await query.answer("❌ Xatolik yuz berdi", show_alert=True)
            elif update.message:
                await update.message.reply_text(
                    "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
                    parse_mode="HTML"
                )
        except:
            pass


async def template_comedy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """🎭 COMEDY SHABLONI - Random kulgili video (YANGI + ESKI)"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['selected_template'] = 'comedy'
    
    # Random prompt tanlash - YANGI COMEDY + ESKI PROMPTS
    selected_prompt = get_random_prompt()
    context.user_data['comedy_name'] = selected_prompt['name']
    context.user_data['comedy_prompt'] = selected_prompt['prompt']
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="wait_for_photo")],
        [InlineKeyboardButton("🔄 Boshqa Prompt", callback_data="template_comedy")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="templates_menu")]
    ]
    
    # ALL_PROMPTS'dan misol ko'rsatish
    sample_prompts = "\n".join([f"• {p['name']}" for p in random.sample(ALL_PROMPTS, min(5, len(ALL_PROMPTS)))])
    
    await query.edit_message_text(
        text="🎭 <b>RANDOM PROMPT - YANGI + ESKI!</b>\n\n"
             f"<b>Tanlangan:</b> {context.user_data.get('comedy_name', selected_prompt['name'])}\n\n"
             "Bu shablonda rasmingiz:\n"
             "• Yangi hazil yoki eski emosyon!\n"
             "• Random har klik!\n"
             "• 28+ ta turli video ko'rik mavjud! 🎉\n\n"
             "<b>Misol prompts:</b>\n"
             f"{sample_prompts}\n\n"
             "Rasm yuboring yoki boshqa promoptni tanlang:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ==========================================
# ℹ️ YORDAM MENYU - HELP MENU
# ==========================================
async def help_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Yordam menyu"""
    query = update.callback_query
    await query.answer()
    
    help_keyboards = [
        [InlineKeyboardButton("📘 Qanday ishlaydi?", callback_data="help_how")],
        [InlineKeyboardButton("📩 Admin bilan bog'lanish", callback_data="help_admin")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_menu")]
    ]
    
    help_markup = InlineKeyboardMarkup(help_keyboards)
    
    await query.edit_message_text(
        text="ℹ️ <b>YORDAM</b>\n\n"
             "Qaysi mavzu haqida bilmoqchi?",
        reply_markup=help_markup,
        parse_mode="HTML"
    )


async def help_how(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Qanday ishlaydi"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("◀️ Orqaga", callback_data="help_menu")]
    ]
    
    await query.edit_message_text(
        text="📘 <b>QANDAY ISHLAYDI?</b>\n\n"
             "<b>1️⃣ Rasm Yuboring</b>\n"
             "Yuqori sifatli rasm yuboring (JPG yoki PNG)\n\n"
             "<b>2️⃣ Shablonni Tanlang</b>\n"
             "Sevgi, Bayram, Oila, Xotira yoki Trend\n\n"
             "<b>3️⃣ Kuting</b>\n"
             "AI rasmni 2-15 daqiqada jonli videoga aylantiradi\n\n"
             "<b>4️⃣ Video Olish</b>\n"
             "Tayyor videoni download qiling!\n\n"
             "<b>⏱️ CHEKLOV:</b> Har 6 soatda 1 ta video",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


async def help_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin bilan bog'lanish"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("◀️ Orqaga", callback_data="help_menu")]
    ]
    
    await query.edit_message_text(
        text="📩 <b>ADMIN BILAN BOG'LANISH</b>\n\n"
             "Agar muammo yoki taklifinggiz bo'lsa:\n\n"
             "<b>👤 Telegram:</b> @diorbek_dev\n"
             "<b>📧 Email:</b> support@jonlantir.uz\n"
             "<b>💬 Telegramm guruh:</b> @jonlantir_ai_group\n\n"
             "Biz sizning fikringizni qadrladik! 🙏",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ==========================================
# 📊 STATISTICS BUTTON
# ==========================================
async def my_stats_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Statistika tugmasi (callback version)"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    user_db.add_user(user.id, user.username, user.first_name)
    stats = user_db.get_user_stats(user.id)
    
    if not stats:
        await query.edit_message_text("Ma'lumot topilmadi.")
        return
    
    # Keyingi video vaqti
    can_create, time_left = user_db.can_create_video(user.id)
    
    is_admin = user.id in ADMIN_IDS
    status = "👑 **ADMIN** (Cheklovsiz)" if is_admin else "👤 **Oddiy foydalanuvchi**"
    
    next_video = ""
    if not can_create and not is_admin:
        hours = int(time_left // 3600)
        minutes = int((time_left % 3600) // 60)
        next_video = f"\n⏰ **Keyingi video:** {hours} soat {minutes} daqiqadan keyin"
    elif is_admin:
        next_video = "\n✅ **Hozir video yarata olasiz!** (Admin)"
    else:
        next_video = "\n✅ **Hozir video yarata olasiz!**"
    
    keyboard = [
        [InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_menu")]
    ]
    
    loyalty_lines = (
        f"💎 {loyalty_profile.get('tier_emoji', '')} {loyalty_profile.get('tier', '')}\n"
        f"   Ballar: <b>{loyalty_profile.get('points', 0)}</b>\n"
        f"   Keyingi daraja: {loyalty_profile.get('points_to_next', 0)} bal\n"
        f"   🎁 Promo tayyor: {loyalty_profile.get('available_promotions', 0)}\n"
    )
    if loyalty_profile.get('cooldown_tokens', 0) > 0:
        loyalty_lines += f"   ⏭️ Bonus token: {loyalty_profile.get('cooldown_tokens')} ta\n"
    
    stats_text = (
        "📊 <b>STATISTIKA</b>\n\n"
        
        f"👤 {stats['first_name']}\n"
        f"🏅 {status}\n\n"
        f"{loyalty_lines}\n"
        
        f"🎬 Videolar: <b>{stats['videos_created']}</b>\n"
        f"{next_video}\n\n"
        
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    await query.edit_message_text(stats_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")


# ==========================================
# 💎 LOYALTY & PROMO MENYU
# ==========================================
def build_loyalty_view(user_id: int):
    profile = user_db.get_loyalty_profile(user_id)
    available_promos = user_db.get_available_promotions(user_id)
    
    tokens_line = f"⏭️ Bonus token: {profile.get('cooldown_tokens', 0)} ta\n" if profile.get('cooldown_tokens') else ""
    multiplier_line = ""
    multiplier = profile.get('multiplier', 1)
    expiry = profile.get('multiplier_expires')
    if multiplier and multiplier > 1 and expiry:
        remaining_hours = max(1, int((expiry - time.time()) // 3600))
        multiplier_line = f"✨ Ball multiplikatori: x{multiplier:.1f} ({remaining_hours} soat)\n"
    
    prompt_unlocks = profile.get('prompt_packs', [])
    prompt_line = ""
    if prompt_unlocks:
        readable_names = [pack.replace('_', ' ').title() for pack in prompt_unlocks]
        prompt_line = "📦 Ochilgan packlar: " + ", ".join(readable_names) + "\n"
    
    lines = [
        "💎 <b>LOYALTY PROGRAM</b>\n",
        f"{profile.get('tier_emoji', '')} <b>{profile.get('tier', '')}</b> — {profile.get('points', 0)} bal",
        f"➡️ Keyingi daraja: {profile.get('points_to_next', 0)} bal",
        tokens_line.strip(),
        multiplier_line.strip(),
        prompt_line.strip(),
        f"🔥 Streak: {profile.get('streak', 0)} kun (eng yaxshi: {profile.get('best_streak', 0)})"
    ]
    
    message = "\n".join(filter(None, lines))
    
    if available_promos:
        message += "\n\n🎁 <b>Mavjud promolar:</b>\n"
        for promo in available_promos[:3]:
            message += (
                f"{promo['name']} — {promo['description']}\n"
                f"🔓 {promo['unlock_points']} bal | ♻️ {promo['cooldown_hours']} soat\n"
            )
    else:
        message += "\n\n🎁 Hozircha promo tayyor emas. Ko'proq ball to'plang!"
    
    keyboard = []
    for promo in available_promos[:3]:
        keyboard.append([InlineKeyboardButton(f"🎁 {promo['name']}", callback_data=f"loyalty_claim:{promo['id']}")])
    
    keyboard.append([
        InlineKeyboardButton("📜 Tarix", callback_data="loyalty_history"),
        InlineKeyboardButton("🔄 Yangilash", callback_data="loyalty_menu")
    ])
    keyboard.append([InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_main_menu")])
    
    return message, keyboard


async def loyalty_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    user_db.add_user(user.id, user.username, user.first_name)
    
    if query:
        await query.answer()
        message, keyboard = build_loyalty_view(user.id)
        await query.edit_message_text(
            text=message,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )


async def loyalty_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    profile = user_db.get_loyalty_profile(user.id)
    history = profile.get('history', [])
    
    if not history:
        history_text = "📜 <b>Loyalty tarixi hozircha bo'sh.</b>"
    else:
        history_lines = ["📜 <b>Oxirgi faoliyat</b>\n"]
        for entry in history[:8]:
            ts = time.strftime("%d.%m %H:%M", time.localtime(entry.get('ts', time.time())))
            history_lines.append(
                f"{ts} • +{entry.get('points', 0)} bal ({entry.get('reason', '-')})"
            )
        history_text = "\n".join(history_lines)
    
    keyboard = [
        [InlineKeyboardButton("◀️ Orqaga", callback_data="loyalty_menu")]
    ]
    
    await query.edit_message_text(
        text=history_text,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def loyalty_claim_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user
    promo_id = query.data.split(":", 1)[1]
    
    success, payload = user_db.claim_promotion(user.id, promo_id)
    if success:
        message = f"{payload['promo']['name']} faollashtirildi!\n{payload['reward_summary']}"
        await query.answer(message, show_alert=True)
    else:
        await query.answer(payload, show_alert=True)
    
    message, keyboard = build_loyalty_view(user.id)
    await query.edit_message_text(
        text=message,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def loyalty_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_db.add_user(user.id, user.username, user.first_name)
    message, keyboard = build_loyalty_view(user.id)
    await update.message.reply_text(
        message,
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ==========================================
# 🎬 VIDEO YARATISH BUTTONLARI
# ==========================================
async def create_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Video yaratish tugmasi"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📸 Rasm Yuboring", callback_data="wait_for_photo")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_menu")]
    ]
    
    await query.edit_message_text(
        text="🎬 <b>VIDEO YARATISH</b>\n\n"
             "Rasm yuboring, shundan so'ng AI uni jonli videoga aylantiradi!\n\n"
             "💡 <b>Maslahat:</b> Yuqori sifatli rasm ishlatish (min 512x512)",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML"
    )


# ==========================================
# ORQAGA TUGMASI
# ==========================================
async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy menyuga qaytish"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    is_admin = user.id in ADMIN_IDS
    admin_badge = " 👑" if is_admin else ""
    
    cheklov_text = "⏰ **Cheklov:** Har 6 soatda 1 ta video" if not is_admin else "👑 **Siz Admin:** Cheklovsiz video yaratish!"
    
    main_menu_text = (
        f"🎬 **Jonlantir AI**{admin_badge}\n\n"
        f"Assalomu alaykum, {user.first_name}!\n\n"
        
        "📸 **Rasm yuboring**\n"
        "🤖 **AI jonli videoga aylantiradi**\n\n"
        
        "🗣️ O'zbekcha ovoz bilan:\n"
        "👴 Bobo | 👵 Buvi | 👨 Ota\n"
        "💕 Ona | 👦 Bola | 👥 Oila\n\n"
        
        f"{cheklov_text}\n\n"
        
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("🎬 Video Yaratish", callback_data="create_video"),
            InlineKeyboardButton("🎨 Shablonlar", callback_data="templates_menu")
        ],
        [
            InlineKeyboardButton("📁 KATEGORIYA", callback_data="category_menu"),
            InlineKeyboardButton("ℹ️ Yordam", callback_data="help_menu")
        ],
        [
            InlineKeyboardButton("📊 Statistika", callback_data="my_stats_button")
        ]
    ]
    
    await query.edit_message_text(
        text=main_menu_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


# ==========================================
# WAIT FOR PHOTO PLACEHOLDER
# ==========================================
async def wait_for_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasmni kutish"""
    try:
        query = update.callback_query
        if query:
            await query.answer()
            
            # State ni o'rnatish - rasm kutayotganimizni belgilash
            context.user_data['waiting_for_photo'] = True
            
            await query.edit_message_text(
                text="📸 <b>RASM YUBORINGMI?</b>\n\n"
                     "Pastdagi chat-da rasm yuboring va AI uni jonli videoga aylantiradi!\n\n"
                     "💡 <i>Yuqori sifatli rasm yuboring (JPG yoki PNG)</i>\n"
                     "⏱️ <i>Video 2-15 daqiqada tayyor bo'ladi</i>",
                parse_mode="HTML"
            )
            logger.info(f"📸 User {update.effective_user.id} - Rasm yuborishni kutmoqda")
        else:
            # Agar query bo'lmasa, oddiy xabar yuborish
            await update.message.reply_text(
                text="📸 <b>RASM YUBORINGMI?</b>\n\n"
                     "Rasm yuboring va AI uni jonli videoga aylantiradi!\n\n"
                     "💡 <i>Yuqori sifatli rasm yuboring (JPG yoki PNG)</i>\n"
                     "⏱️ <i>Video 2-15 daqiqada tayyor bo'ladi</i>",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"❌ Error in wait_for_photo: {e}")
        try:
            query = update.callback_query
            if query:
                await query.answer("❌ Xatolik yuz berdi", show_alert=True)
            elif update.message:
                await update.message.reply_text(
                    "❌ Xatolik yuz berdi. Qaytadan urinib ko'ring.",
                    parse_mode="HTML"
                )
        except:
            pass


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command"""
    help_text = (
        "📖 **Yordam**\n\n"
        
        "**1.** Rasm yuboring\n"
        "**2.** 2-15 daqiqa kuting\n"
        "**3.** Video tayyor!\n\n"
        
        "🎭 **Ovozlar:**\n"
        "👴 Bobo | 👵 Buvi | 👨 Ota\n"
        "💕 Ona | 👦 Bola | 👥 Oila\n\n"
        
        "⏰ Har 6 soatda 1 video\n\n"
        
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    await update.message.reply_text(help_text, parse_mode='Markdown')


async def scenarios_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /scenarios command"""
    scenarios_text = (
        "🎭 **Stsenariylar**\n\n"
        
        "AI rasmni o'rganib tanlaydi:\n\n"
        
        "👴 Bobo — hikmat va xotiralar\n"
        "👵 Buvi — duo va nasihаt\n"
        "👨 Ota — hayotiy maslahat\n"
        "💕 Ona — mehr va muhabbat\n"
        "👦 Bola — quvonch va orzular\n"
        "👥 Oila — oilaviy muhabbat\n\n"
        
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    await update.message.reply_text(scenarios_text, parse_mode='Markdown')


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for text messages - TEXT TO IMAGE VA EDIT IMAGE"""
    user = update.effective_user
    text = update.message.text
    
    # Agar broadcast kutilayotgan bo'lsa, uni handle qilmas
    if context.user_data.get('waiting_for_broadcast'):
        return
    
    waiting_for = context.user_data.get('waiting_for')
    
    # TEXT FOR VIDEO (MATN ORQALI VIDEO)
    if waiting_for == 'text_for_video':
        video_image_bytes = context.user_data.get('video_image_bytes')
        
        if not video_image_bytes:
            await update.message.reply_text(
                "❌ **Rasm topilmadi**\n\n"
                "Qaytadan boshlang:\n"
                "1. /start ni bosing\n"
                "2. 🎬 Video Yaratish → 📝 Matn orqali\n"
                "3. Rasmni yuboring\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            context.user_data.pop('waiting_for', None)
            return
        
        # Check video creation limit
        can_create, time_left = user_db.can_create_video(user.id, consume_loyalty_skip=True)
        
        if not can_create:
            hours = int(time_left // 3600)
            minutes = int((time_left % 3600) // 60)
            
            await update.message.reply_text(
                "┏━━━━━━━━━━━━━━━━━━━┓\n"
                "┃ ⏳ **KUTISH VAQTI** ⏳ ┃\n"
                "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
                f"⚠️ Siz allaqachon video yaratgansiz!\n\n"
                f"🕐 **Keyingi video:** {hours} soat {minutes} daqiqadan keyin\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🤖 @Jonlantir_Ai_bot\n"
                f"━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            context.user_data.pop('waiting_for', None)
            context.user_data.pop('video_image_bytes', None)
            return
        
        wait_msg = await update.message.reply_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ 🎬 **VIDEO YARATILMOQDA** ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            "🎨 AI video yaratyapti...\n"
            "📊 Matn tahlil qilinmoqda\n"
            "🎯 Sizning tavsifingiz qo'llanmoqda\n\n"
            "⏳ *2-15 daqiqa...*",
            parse_mode='Markdown'
        )
        
        try:
            # Use user's text as custom prompt for video creation
            custom_prompt = text.strip()
            logger.info(f"🎬 Creating text-based video for user {user.id}: {custom_prompt[:100]}")
            
            # Create video using the existing video creation logic
            # but with custom prompt instead of random
            session = requests.Session()
            session.trust_env = False
            
            # Get access token
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_SERVICE_ACCOUNT_FILE,
                scopes=['https://www.googleapis.com/auth/cloud-platform']
            )
            credentials.refresh(Request())
            access_token = credentials.token
            
            # Upload image to GCS
            upload_url = f"https://storage.googleapis.com/upload/storage/v1/b/jonlantir-test/o?uploadType=media&name=user_images/{user.id}_{int(time.time())}.jpg"
            upload_headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'image/jpeg'
            }
            
            upload_response = session.post(upload_url, headers=upload_headers, data=video_image_bytes, timeout=30)
            upload_response.raise_for_status()
            
            gcs_image_uri = f"gs://jonlantir-test/user_images/{user.id}_{int(time.time())}.jpg"
            logger.info(f"✅ Image uploaded to GCS: {gcs_image_uri}")
            
            # Create video with CUSTOM PROMPT
            veo_url = f"https://{GOOGLE_LOCATION}-aiplatform.googleapis.com/v1/projects/{GOOGLE_PROJECT_ID}/locations/{GOOGLE_LOCATION}/publishers/google/models/veo-001:generateContent"
            
            veo_payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [
                            {
                                "fileData": {
                                    "mimeType": "image/jpeg",
                                    "fileUri": gcs_image_uri
                                }
                            },
                            {
                                "text": custom_prompt  # Use user's custom text
                            }
                        ]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.4,
                    "topP": 0.95,
                    "topK": 40,
                    "maxOutputTokens": 8192
                }
            }
            
            veo_headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            logger.info(f"🎬 Sending custom video request to Veo API for user {user.id}")
            veo_response = session.post(veo_url, json=veo_payload, headers=veo_headers, timeout=120)
            veo_response.raise_for_status()
            veo_data = veo_response.json()
            
            # Get video URL
            video_uri = None
            if 'candidates' in veo_data and len(veo_data['candidates']) > 0:
                parts = veo_data['candidates'][0].get('content', {}).get('parts', [])
                for part in parts:
                    if 'fileData' in part:
                        video_uri = part['fileData'].get('fileUri')
                        break
            
            if not video_uri:
                raise Exception("Video URI not found in response")
            
            logger.info(f"✅ Video created: {video_uri}")
            
            # Download video from GCS
            gcs_path = video_uri.replace('gs://', '')
            bucket_name = gcs_path.split('/')[0]
            blob_path = '/'.join(gcs_path.split('/')[1:])
            
            download_url = f"https://storage.googleapis.com/storage/v1/b/{bucket_name}/o/{blob_path.replace('/', '%2F')}?alt=media"
            download_headers = {'Authorization': f'Bearer {access_token}'}
            
            video_response = session.get(download_url, headers=download_headers, timeout=60)
            video_response.raise_for_status()
            video_bytes = video_response.content
            
            logger.info(f"✅ Video downloaded: {len(video_bytes)} bytes")
            
            # Send video to user
            await update.message.reply_video(
                video=video_bytes,
                caption=(
                    "✅ **Video tayyor!**\n\n"
                    f"📝 _{custom_prompt[:100]}{'...' if len(custom_prompt) > 100 else ''}_\n\n"
                    "🎬 Sizning tavsifingiz bo'yicha\n"
                    "🤖 Google Veo 2\n\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "🤖 @Jonlantir_Ai_bot\n"
                    "━━━━━━━━━━━━━━━━━━"
                ),
                parse_mode='Markdown'
            )
            
            # Record video creation
            loyalty_update = user_db.record_video_creation(user.id, reason='text_video')
            if loyalty_update:
                await update.message.reply_text(
                    f"💎 {loyalty_update.get('tier_emoji', '')} {loyalty_update.get('tier', '')} — "
                    f"+{loyalty_update.get('points_added', 0)} bal\n"
                    f"📈 Jami: {loyalty_update.get('total_points', 0)} bal",
                    parse_mode='Markdown'
                )
            
            await wait_msg.delete()
            context.user_data.pop('waiting_for', None)
            context.user_data.pop('video_image_bytes', None)
            logger.info(f"✅ Successfully created text-based video for user {user.id}")
            return
            
        except Exception as e:
            logger.error(f"Text-based video creation error: {e}", exc_info=True)
            await wait_msg.edit_text(
                "❌ **Xatolik yuz berdi**\n\n"
                "Video yaratib bo'lmadi.\n"
                "Qaytadan urinib ko'ring.\n\n"
                "💡 **Maslahat:**\n"
                "• Inglizchada yozing\n"
                "• Oddiy va aniq bo'lsin\n"
                "• Harakat va gaplarni kiriting\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            context.user_data.pop('waiting_for', None)
            context.user_data.pop('video_image_bytes', None)
        
        return
    
    # TEXT TO IMAGE
    if waiting_for == 'text_for_image':
        wait_msg = await update.message.reply_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ ✍️ **RASM YARATILMOQDA** ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            "🎨 AI rasm yaratyapti...\n"
            "📊 Tavsif tahlil qilinmoqda\n"
            "🎯 Sifat nazorati faol\n\n"
            "⏳ *30-60 soniya...*",
            parse_mode='Markdown'
        )
        
        try:
            # Generate image with enhanced Gemini
            logger.info(f"🎨 Generating image for user {user.id}: {text[:100]}")
            result = imagen_generator.generate_image(text)
            
            if result and result.get('success') and 'image_bytes' in result:
                image_bytes = result['image_bytes']
                
                loyalty_bonus = user_db.add_loyalty_points(
                    user.id,
                    LOYALTY_POINT_RULES.get('image_generation'),
                    reason='image_generation'
                )
                loyalty_caption = ""
                if loyalty_bonus:
                    loyalty_caption = (
                        f"\n💎 {loyalty_bonus.get('tier_emoji', '')} {loyalty_bonus.get('tier', '')} — "
                        f"+{loyalty_bonus.get('points_added', 0)} bal"
                        f"\n📈 Jami: {loyalty_bonus.get('total_points', 0)} bal"
                    )
                
                # Send image with detailed caption
                await update.message.reply_photo(
                    photo=image_bytes,
                    caption=(
                        "✅ **Rasm tayyor!**\n\n"
                        f"📝 _{text[:80]}{'...' if len(text) > 80 else ''}_\n\n"
                        "🎯 **Sifat:**\n"
                        "• 4K resolution\n"
                        "• Tabiiy proporsiyalar\n"
                        "• Professional chiqish\n\n"
                        f"🤖 Google Gemini 2.0{loyalty_caption}\n\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "🤖 @Jonlantir_Ai_bot\n"
                        "━━━━━━━━━━━━━━━━━━"
                    ),
                    parse_mode='Markdown'
                )
                
                await wait_msg.delete()
                context.user_data.pop('waiting_for', None)
                logger.info(f"✅ Successfully generated image for user {user.id}")
                return
            
            await wait_msg.edit_text(
                "❌ **Xatolik**\n\n"
                "Rasm yaratib bo'lmadi.\n\n"
                "💡 **Maslahatlar:**\n"
                "• Inglizchada yozing\n"
                "• Aniqroq tavsif bering\n"
                "• Stil ko'rsating (realistic, cartoon, etc.)\n\n"
                "🔄 Qaytadan urinib ko'ring\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            logger.warning(f"❌ Failed to generate image for user {user.id}")
        except Exception as e:
            logger.error(f"Gemini text to image error: {e}", exc_info=True)
            await wait_msg.edit_text(
                "❌ **Xatolik yuz berdi**\n\n"
                "Qaytadan urinib ko'ring.\n"
                "Agar muammo davom etsa,\n"
                "admin bilan bog'laning.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
        
        return
    
    # IMAGE EDITING - waiting for edit instruction
    elif waiting_for == 'edit_instruction':
        edit_image_bytes = context.user_data.get('edit_image_bytes')
        
        if not edit_image_bytes:
            await update.message.reply_text(
                "❌ **Rasm topilmadi**\n\n"
                "Qaytadan boshlang:\n"
                "1. /start ni bosing\n"
                "2. 🎨 Rasmni O'zgartir tanlang\n"
                "3. Rasmni yuboring\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            context.user_data.pop('waiting_for', None)
            return
        
        wait_msg = await update.message.reply_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ 🎨 **RASM O'ZGARTIRILMOQDA** ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            "✨ AI rasm tahrir qilyapti...\n"
            "🔍 Asl rasm tahlil qilinmoqda\n"
            "🛡️ Yuz va identifikatsiya saqlanmoqda\n"
            "🎯 Faqat so'ralgan o'zgarish qo'llanmoqda\n\n"
            "⏳ *30-60 soniya...*",
            parse_mode='Markdown'
        )
        
        try:
            # Edit image with enhanced Gemini
            logger.info(f"🎨 Editing image for user {user.id}: {text[:100]}")
            result = imagen_generator.edit_image(edit_image_bytes, text)
            
            if result and result.get('success') and 'image_bytes' in result:
                edited_bytes = result['image_bytes']
                
                loyalty_bonus = user_db.add_loyalty_points(
                    user.id,
                    LOYALTY_POINT_RULES.get('image_edit'),
                    reason='image_edit'
                )
                loyalty_caption = ""
                if loyalty_bonus:
                    loyalty_caption = (
                        f"\n💎 {loyalty_bonus.get('tier_emoji', '')} {loyalty_bonus.get('tier', '')} — "
                        f"+{loyalty_bonus.get('points_added', 0)} bal"
                        f"\n📈 Jami: {loyalty_bonus.get('total_points', 0)} bal"
                    )
                
                # Send edited image with detailed caption
                await update.message.reply_photo(
                    photo=edited_bytes,
                    caption=(
                        "✅ **Rasm o'zgartirildi!**\n\n"
                        f"📝 _{text[:80]}{'...' if len(text) > 80 else ''}_\n\n"
                        "🎯 **Saqlanganlar:**\n"
                        "• Asl yuz va identifikatsiya ✓\n"
                        "• Tabiiy proporsiyalar ✓\n"
                        "• Yorug'lik va soyalar ✓\n"
                        "• Sifatsiz tahrirlash ✓\n\n"
                        f"🤖 Google Gemini 2.0{loyalty_caption}\n\n"
                        "━━━━━━━━━━━━━━━━━━\n"
                        "🤖 @Jonlantir_Ai_bot\n"
                        "━━━━━━━━━━━━━━━━━━"
                    ),
                    parse_mode='Markdown'
                )
                
                await wait_msg.delete()
                context.user_data.pop('waiting_for', None)
                context.user_data.pop('edit_image_bytes', None)
                logger.info(f"✅ Successfully edited image for user {user.id}")
                return
            
            await wait_msg.edit_text(
                "❌ **Xatolik**\n\n"
                "Rasm o'zgartirib bo'lmadi.\n\n"
                "💡 **Maslahatlar:**\n"
                "• Inglizchada yozing\n"
                "• Aniq va qisqa ko'rsatma bering\n"
                "• Bitta narsani o'zgartiring\n"
                "• Oddiy so'zlar ishlating\n\n"
                "📝 **Yaxshi misollar:**\n"
                "• \"Add sunset background\"\n"
                "• \"Change hair color to blonde\"\n"
                "• \"Add flowers in foreground\"\n\n"
                "🔄 Qaytadan urinib ko'ring\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
            logger.warning(f"❌ Failed to edit image for user {user.id}")
        except Exception as e:
            logger.error(f"Gemini image edit error: {e}", exc_info=True)
            await wait_msg.edit_text(
                "❌ **Xatolik yuz berdi**\n\n"
                "Qaytadan urinib ko'ring.\n"
                "Agar muammo davom etsa,\n"
                "admin bilan bog'laning.\n\n"
                "━━━━━━━━━━━━━━━━━━\n"
                "🤖 @Jonlantir_Ai_bot\n"
                "━━━━━━━━━━━━━━━━━━",
                parse_mode='Markdown'
            )
        
        return
    
    # Default message
    await update.message.reply_text(
        "📸 **Rasm yuboring**\n\n"
        "yoki /start bosing\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━",
        parse_mode='Markdown'
    )


# ==========================================
# 📋 ASOSIY MENYU HANDLERS
# ==========================================

async def menu_video_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Video Yaratish submenu - 2 variant"""
    query = update.callback_query
    await query.answer()
    
    message = (
        "╔══════════════════════╗\n"
        "║ 🎬 **VIDEO YARATISH** ║\n"
        "╚══════════════════════╝\n\n"
        
        "📹 **Video yaratish usulini tanlang:**\n\n"
        
        "1️⃣ **Matn orqali** — Siz tavsif bering\n"
        "   • Rasm yuboring\n"
        "   • Video qanday bo'lishini yozing\n"
        "   • Sifatli video tayyorlanadi\n\n"
        
        "2️⃣ **Tasodifiy** — AI o'zi tanlaydi\n"
        "   • Rasm yuboring\n"
        "   • Random komediya stili\n"
        "   • Kutilmagan video!\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 Matn orqali Video", callback_data="menu_text_video")],
        [InlineKeyboardButton("🎲 Tasodifiy Video", callback_data="menu_random_video")],
        [InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_main_menu")]
    ]
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))


async def menu_text_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matn orqali video yaratish"""
    query = update.callback_query
    await query.answer()
    
    message = (
        "╔══════════════════════╗\n"
        "║ 📝 **MATN ORQALI VIDEO** ║\n"
        "╚══════════════════════╝\n\n"
        
        "📸 **1-QADAM: Rasmni yuboring**\n\n"
        
        "Keyin sizdan so'raladi:\n"
        "• Video qanday bo'lishini yozing\n"
        "• Qanday harakat qilishini\n"
        "• Nima deyishini\n"
        "• Qanday kayfiyatda\n\n"
        
        "✨ **Misol:**\n"
        "_\"Kulgi bilan salom aytsin, qo'l silkitsin, \"_\n"
        "_\"keyin jiddiy bo'lib, sog'inch bildirib gapirsin\"_\n\n"
        
        "💡 **Maslahat:**\n"
        "• Inglizchada yozing (yaxshiroq natija)\n"
        "• Aniq va batafsil\n"
        "• Harakat va gaplarni kiriting\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Orqaga", callback_data="menu_video_creation")]]
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['waiting_for'] = 'photo_for_text_video'


async def menu_random_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tasodifiy video yaratish"""
    query = update.callback_query
    await query.answer()
    
    message = (
        "╔══════════════════════╗\n"
        "║ 🎲 **TASODIFIY VIDEO** ║\n"
        "╚══════════════════════╝\n\n"
        
        "📸 **Rasmni yuboring**\n\n"
        
        "Bot avtomatik:\n"
        "✅ Tasodifiy komediya stilini tanlaydi\n"
        "✅ O'zbek tilida gapiradi\n"
        "✅ Kulgili va jonli video yaratadi\n"
        "✅ HD sifatda qaytaradi\n\n"
        
        "🎭 **Variantlar:**\n"
        "• Hayron qolganlik\n"
        "• Kulgili prikol\n"
        "• Sho'x va o'ychan\n"
        "• Cool va jiddiy\n"
        "• ... va boshqalar!\n\n"
        
        "🎯 **Har safar yangi stil!**\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Orqaga", callback_data="menu_video_creation")]]
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['waiting_for'] = 'photo_for_random_video'


async def menu_text_to_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Matn → Rasm menu with comprehensive instructions"""
    query = update.callback_query
    await query.answer()
    
    message = (
        "╔══════════════════════╗\n"
        "║ ✍️ **MATN → RASM** ║\n"
        "╚══════════════════════╝\n\n"
        
        "✍️ **Matn yozing, AI rasm yaratadi!**\n\n"
        
        "🎯 **Nimalar qo'llaniladi:**\n"
        "• 4K sifatli rasm\n"
        "• Tabiiy proporsiyalar\n"
        "• Professional chiqish\n"
        "• Hech qanday tekst/watermark\n\n"
        
        "🎨 **Stillar:**\n"
        "• _realistic_ - Haqiqiy foto\n"
        "• _cartoon_ - Multfilm\n"
        "• _cinematic_ - Kino\n"
        "• _minimalistic_ - Oddiy\n\n"
        
        "📝 **Misollar:**\n"
        "• _\"Realistic sunset in mountains, 4K\"_\n"
        "• _\"Cartoon cat playing guitar\"_\n"
        "• _\"Cinematic futuristic city at night\"_\n"
        "• _\"Minimalistic modern house\"_\n\n"
        
        "💡 **Maslahat:** Inglizchada yozing\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_main_menu")]]
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['waiting_for'] = 'text_for_image'


async def menu_edit_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Rasmni O'zgartirish menu with strict editing rules"""
    query = update.callback_query
    await query.answer()
    
    message = (
        "╔══════════════════════╗\n"
        "║ 🎨 **RASMNI O'ZGARTIR** ║\n"
        "╚══════════════════════╝\n\n"
        
        "📸 **1) Rasmni yuboring**\n"
        "📝 **2) O'zgartirish matnini yozing**\n\n"
        
        "🛡️ **Saqlanadi:**\n"
        "• Yuz va identifikatsiya\n"
        "• Tabiiy proporsiyalar\n"
        "• Yorug'lik va soyalar\n"
        "• Asl tarkib va kompozitsiya\n\n"
        
        "✅ **O'zgartirishlar:**\n"
        "• Fon o'zgartirish\n"
        "• Ob'ekt qo'shish/o'chirish\n"
        "• Rang o'zgartirish\n"
        "• Stil o'zgartirish\n\n"
        
        "📝 **TO'G'RI misollar:**\n"
        "• _\"Add sunset background\"_\n"
        "• _\"Change to cartoon style\"_\n"
        "• _\"Add flowers in foreground\"_\n"
        "• _\"Remove background objects\"_\n\n"
        
        "⚠️ **Muhim:**\n"
        "• Inglizchada yozing\n"
        "• Aniq va qisqa\n"
        "• Bitta narsani o'zgartiring\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [[InlineKeyboardButton("◀️ Orqaga", callback_data="back_to_main_menu")]]
    await query.edit_message_text(message, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data['waiting_for'] = 'photo_for_edit'


async def back_to_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asosiy menyuga qaytish"""
    query = update.callback_query
    await query.answer()
    
    user = query.from_user
    is_admin = user.id in ADMIN_IDS
    admin_badge = " 👑" if is_admin else ""
    
    welcome_message = (
        f"╔══════════════════════╗\n"
        f"║ 🎬 **Jonlantir AI** {admin_badge} ║\n"
        f"╚══════════════════════╝\n\n"
        
        f"👋 Salom, **{user.first_name}**!\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✨ **ASOSIY MENYU**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        "🎬 **Video Yaratish** — 2 usulda video\n"
        "✍️ **Matn → Rasm** — Matndan rasm\n"
        "🎨 **Rasmni O'zgartir** — AI editing\n\n"
        
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    keyboard = [
        [InlineKeyboardButton("🎬 Video Yaratish", callback_data="menu_video_creation")],
        [InlineKeyboardButton("✍️ Matn → Rasm", callback_data="menu_text_to_image"),
         InlineKeyboardButton("🎨 Rasmni O'zgartir", callback_data="menu_edit_image")],
        [InlineKeyboardButton("🎁 Mukofotlar", callback_data="loyalty_menu"),
         InlineKeyboardButton("📊 Statistika", callback_data="my_stats_button")],
        [InlineKeyboardButton("ℹ️ Yordam", callback_data="help_menu")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    context.user_data.pop('waiting_for', None)
    context.user_data.pop('edit_image_bytes', None)
    context.user_data.pop('video_image_bytes', None)
    context.user_data.pop('random_video_mode', None)
    
    await query.edit_message_text(welcome_message, parse_mode='Markdown', reply_markup=reply_markup)


# ==========================================
# ✍️ TEXT TO IMAGE & EDITING - GOOGLE GEMINI  
# ==========================================

class GoogleGeminiImageGenerator:
    """Advanced AI system for image generation and editing with strict quality control"""
    
    def __init__(self):
        """Initialize Gemini image generator"""
        self.generation_model = None
        self.vision_model = None
        
        try:
            # Gemini 2.0 Flash Experimental for image generation
            self.generation_model = genai.GenerativeModel('gemini-2.0-flash-exp')
            # Gemini 1.5 Flash for vision/editing tasks
            self.vision_model = genai.GenerativeModel('gemini-1.5-flash')
            logger.info("✅ Google Gemini models initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini: {e}")
    
    def generate_image(self, prompt):
        """
        Generate high-quality, realistic or stylistically correct image from text description.
        
        Rules:
        - Extract main details: subject, environment, style, mood, colors, perspective
        - Produce clean, sharp, 4K-quality image
        - NO text inside image unless requested
        - NO distorted human faces or body proportions
        - Complete short descriptions logically while staying faithful to meaning
        """
        try:
            if not self.generation_model:
                logger.error("Gemini generation model not initialized")
                return None
            
            # Parse and enhance prompt based on requirements
            enhanced_prompt = self._enhance_generation_prompt(prompt)
            logger.info(f"📝 Gemini generation prompt: {enhanced_prompt[:150]}...")
            
            # Generate image with Gemini
            response = self.generation_model.generate_content(
                enhanced_prompt,
                generation_config=genai.GenerationConfig(
                    temperature=0.3,  # Lower for more consistent quality
                    top_p=0.9,
                    top_k=40,
                    max_output_tokens=8192,
                )
            )
            
            # Check if response contains image
            if response and hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        # Return image bytes
                        image_data = part.inline_data.data
                        logger.info(f"✅ Gemini generated image: {len(image_data)} bytes")
                        return {'image_bytes': image_data, 'success': True}
            
            logger.warning("Gemini didn't return image")
            return None
            
        except Exception as e:
            logger.error(f"Gemini generation error: {e}", exc_info=True)
            return None
    
    def edit_image(self, image_bytes, prompt):
        """
        Edit existing image based on user instructions.
        
        Rules:
        - Edit ONLY what user asked for
        - Keep original faces, identity, background, composition unless requested to change
        - Make realistic, seamless edits with no artifacts
        - Keep proportions natural
        - Apply simplest and most logical interpretation if unclear
        - Maintain consistent lighting and shadows
        - Don't add extra objects unless user asks
        """
        try:
            if not self.vision_model:
                logger.error("Gemini vision model not initialized")
                return None
            
            # Optimize image first
            image_bytes = self._optimize_image(image_bytes)
            
            # Enhance prompt with strict editing rules
            enhanced_prompt = self._enhance_edit_prompt(prompt)
            logger.info(f"📝 Gemini edit prompt: {enhanced_prompt[:150]}...")
            
            # Load image from bytes
            img = Image.open(io.BytesIO(image_bytes))
            
            # Create detailed prompt for image editing with preservation rules
            edit_instruction = (
                f"You are an expert image editor. Your task is to edit this image following these STRICT rules:\n\n"
                f"EDITING INSTRUCTION: {enhanced_prompt}\n\n"
                f"PRESERVATION RULES (CRITICAL):\n"
                f"1. Keep ALL original faces, identity, and facial features UNCHANGED unless specifically requested\n"
                f"2. Maintain the original background and composition UNLESS explicitly asked to change\n"
                f"3. Preserve natural body proportions and anatomy\n"
                f"4. Keep consistent lighting and shadows with the original image\n"
                f"5. Make seamless, realistic edits with NO artifacts or distortions\n"
                f"6. Do NOT add extra objects unless the user specifically requests them\n"
                f"7. Apply ONLY the requested changes - nothing more, nothing less\n\n"
                f"OUTPUT: Generate a high-quality edited image that incorporates ONLY the requested changes "
                f"while preserving everything else from the original."
            )
            
            # Use Gemini for vision + generation
            response = self.generation_model.generate_content(
                [edit_instruction, img],
                generation_config=genai.GenerationConfig(
                    temperature=0.2,  # Very low for faithful editing
                    top_p=0.85,
                    top_k=30,
                    max_output_tokens=8192,
                )
            )
            
            # Extract image from response
            if response and hasattr(response, 'candidates') and response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        image_data = part.inline_data.data
                        logger.info(f"✅ Gemini edited image: {len(image_data)} bytes")
                        return {'image_bytes': image_data, 'success': True}
            
            logger.warning("Gemini didn't return edited image")
            return None
            
        except Exception as e:
            logger.error(f"Gemini edit error: {e}", exc_info=True)
            return None
    
    def _optimize_image(self, image_bytes):
        """Optimize image for better results while maintaining quality"""
        try:
            img = Image.open(io.BytesIO(image_bytes))
            
            # Convert to RGB
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Resize if needed (optimal: 1024x1024 for Gemini, but maintain aspect ratio)
            width, height = img.size
            max_size = 1536  # Higher for better quality
            min_size = 512
            
            if width < min_size or height < min_size:
                scale = max(min_size / width, min_size / height)
                new_size = (int(width * scale), int(height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"📐 Upscaled: {width}x{height} → {new_size}")
            elif width > max_size or height > max_size:
                scale = min(max_size / width, max_size / height)
                new_size = (int(width * scale), int(height * scale))
                img = img.resize(new_size, Image.Resampling.LANCZOS)
                logger.info(f"📐 Downscaled: {width}x{height} → {new_size}")
            
            # Save optimized with higher quality
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=98)
            return output.getvalue()
            
        except Exception as e:
            logger.warning(f"Image optimization failed: {e}")
            return image_bytes
    
    def _detect_style(self, prompt):
        """Detect requested style from prompt"""
        prompt_lower = prompt.lower()
        
        style_keywords = {
            'realistic': ['realistic', 'photorealistic', 'photo', 'real life', 'lifelike'],
            'cartoon': ['cartoon', 'animated', 'animation', 'toon', 'comic'],
            'cinematic': ['cinematic', 'movie', 'film', 'dramatic lighting'],
            'minimalistic': ['minimalistic', 'minimal', 'simple', 'clean'],
            'artistic': ['artistic', 'art', 'painting', 'painted'],
            'sketch': ['sketch', 'drawing', 'pencil', 'hand-drawn'],
            '3d': ['3d', 'three dimensional', 'cgi', 'rendered'],
            'vintage': ['vintage', 'retro', 'old', 'classic'],
            'modern': ['modern', 'contemporary', 'sleek'],
            'fantasy': ['fantasy', 'magical', 'mystical', 'ethereal'],
        }
        
        for style, keywords in style_keywords.items():
            for keyword in keywords:
                if keyword in prompt_lower:
                    return style
        
        return 'realistic'  # Default to realistic
    
    def _enhance_generation_prompt(self, user_prompt):
        """
        Enhance prompt for image generation with detailed quality controls.
        
        Extract: subject, environment, style, mood, colors, perspective
        """
        prompt = user_prompt.strip()
        
        # Detect style from prompt
        detected_style = self._detect_style(prompt)
        
        # Style-specific enhancements
        style_enhancements = {
            'realistic': (
                "photorealistic, ultra-detailed, 4K quality, natural lighting, "
                "professional photography, correct human anatomy, realistic skin texture, "
                "perfect proportions, sharp focus, high detail"
            ),
            'cartoon': (
                "cartoon style, animated, vibrant colors, clean lines, "
                "stylized but proportional, expressive, smooth shading"
            ),
            'cinematic': (
                "cinematic composition, dramatic lighting, movie quality, "
                "depth of field, atmospheric, professional color grading, epic scene"
            ),
            'minimalistic': (
                "minimalistic design, clean composition, simple elements, "
                "elegant, uncluttered, modern aesthetic, balanced"
            ),
            'artistic': (
                "artistic style, creative interpretation, painterly quality, "
                "harmonious colors, artistic composition, expressive brushwork"
            ),
            'sketch': (
                "sketch style, hand-drawn appearance, pencil lines, artistic strokes, "
                "natural drawing technique"
            ),
            '3d': (
                "3D rendered, CGI quality, detailed textures, realistic materials, "
                "professional 3D modeling, smooth surfaces, proper lighting"
            ),
            'vintage': (
                "vintage aesthetic, classic style, nostalgic feel, "
                "period-appropriate details, timeless quality"
            ),
            'modern': (
                "modern design, contemporary style, sleek appearance, "
                "current trends, polished look"
            ),
            'fantasy': (
                "fantasy style, magical atmosphere, imaginative elements, "
                "ethereal quality, creative interpretation"
            )
        }
        
        style_enhancement = style_enhancements.get(detected_style, style_enhancements['realistic'])
        
        # Build comprehensive prompt
        enhanced = (
            f"Create a high-quality, detailed image: {prompt}\n\n"
            f"STYLE: {style_enhancement}\n\n"
            f"QUALITY REQUIREMENTS:\n"
            f"- Clean, sharp, 4K resolution\n"
            f"- Perfect composition and framing\n"
            f"- Natural proportions (especially for humans - NO distorted faces or bodies)\n"
            f"- Proper perspective and depth\n"
            f"- Harmonious color palette\n"
            f"- Professional-grade output\n"
            f"- NO text/watermarks/signatures inside the image unless specifically requested\n"
            f"- NO artifacts or distortions\n\n"
            f"OUTPUT: Produce the final, complete image based on the description."
        )
        
        return enhanced
    
    def _enhance_edit_prompt(self, user_prompt):
        """
        Enhance prompt for image editing with preservation rules.
        """
        prompt = user_prompt.strip()
        
        # Detect style request in editing
        detected_style = self._detect_style(prompt)
        
        enhanced = (
            f"EDIT REQUEST: {prompt}\n\n"
            f"EDITING STYLE: {detected_style}\n\n"
            f"QUALITY REQUIREMENTS:\n"
            f"- Maintain HIGH quality and resolution\n"
            f"- Keep original proportions natural\n"
            f"- Ensure seamless, realistic integration\n"
            f"- Consistent lighting and shadows with original\n"
            f"- NO visible artifacts or distortions\n"
            f"- NO text added unless specifically requested\n"
            f"- Professional, polished result"
        )
        
        return enhanced


# Initialize Gemini generator
imagen_generator = GoogleGeminiImageGenerator()


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Global error handler"""
    logger.error(f"Exception while handling an update: {context.error}")
    
    # Foydalanuvchiga xabar yuborish
    try:
        await context.bot.send_message(
            chat_id=update.effective_user.id if update.effective_user else None,
            text="❌ **Xatolik**\n\n"
                 "Qaytadan urinib ko'ring.\n\n"
                 "━━━━━━━━━━━━━━━━━━\n"
                 "🤖 @Jonlantir_Ai_bot\n"
                 "━━━━━━━━━━━━━━━━━━",
            parse_mode='Markdown'
        )
    except:
        pass


def main():
    """Start the bot"""
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set!")
        return
    
    if not GOOGLE_PROJECT_ID:
        print("❌ GOOGLE_PROJECT_ID not set!")
        return
    
    if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE):
        print(f"❌ {GOOGLE_SERVICE_ACCOUNT_FILE} not found!")
        return
    
    # Clean proxy settings
    for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        os.environ.pop(var, None)
    
    print("🔍 Ulanish tekshirilmoqda...")
    token = veo_generator.get_access_token()
    if not token:
        print("❌ Ulanish xatosi!")
        return
    print("✅ Ulanish muvaffaqiyatli!")
    
    try:
        # PARALLEL PROCESSING - Ko'p foydalanuvchilar uchun optimallashtirilgan
        application = (
            Application.builder()
            .token(TELEGRAM_BOT_TOKEN)
            .concurrent_updates(True)  # Parallel updates
            .build()
        )
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("scenarios", scenarios_command))
        application.add_handler(CommandHandler("admin", admin_panel))
        application.add_handler(CommandHandler("stats", my_stats))
        application.add_handler(CommandHandler("loyalty", loyalty_command))
        
        # ASOSIY MENYU CALLBACKS - YANGI!
        # New video creation menu handlers
        application.add_handler(CallbackQueryHandler(menu_video_creation, pattern="^menu_video_creation$"))
        application.add_handler(CallbackQueryHandler(menu_text_video, pattern="^menu_text_video$"))
        application.add_handler(CallbackQueryHandler(menu_random_video, pattern="^menu_random_video$"))
        
        # Image generation and editing handlers
        application.add_handler(CallbackQueryHandler(menu_text_to_image, pattern="^menu_text_to_image$"))
        application.add_handler(CallbackQueryHandler(menu_edit_image, pattern="^menu_edit_image$"))
        application.add_handler(CallbackQueryHandler(back_to_main_menu, pattern="^back_to_main_menu$"))
        application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
        
        # MENYU CALLBACK HANDLERS
        application.add_handler(CallbackQueryHandler(templates_menu, pattern="^templates_menu$"))
        application.add_handler(CallbackQueryHandler(category_menu, pattern="^category_menu$"))
        
        # KATEGORIYA CALLBACKS
        application.add_handler(CallbackQueryHandler(cat_funny, pattern="^cat_funny$"))
        application.add_handler(CallbackQueryHandler(cat_nostalgic, pattern="^cat_nostalgic$"))
        application.add_handler(CallbackQueryHandler(cat_festive, pattern="^cat_festive$"))
        application.add_handler(CallbackQueryHandler(cat_emotional, pattern="^cat_emotional$"))
        application.add_handler(CallbackQueryHandler(cat_dramatic, pattern="^cat_dramatic$"))
        application.add_handler(CallbackQueryHandler(cat_retro, pattern="^cat_retro$"))
        application.add_handler(CallbackQueryHandler(cat_sentimental, pattern="^cat_sentimental$"))
        application.add_handler(CallbackQueryHandler(cat_party, pattern="^cat_party$"))
        application.add_handler(CallbackQueryHandler(cat_soft_sad, pattern="^cat_soft_sad$"))
        application.add_handler(CallbackQueryHandler(cat_strong_dramatic, pattern="^cat_strong_dramatic$"))
        application.add_handler(CallbackQueryHandler(cat_boss_confident, pattern="^cat_boss_confident$"))
        application.add_handler(CallbackQueryHandler(cat_upload_photo, pattern="^cat_upload_photo$"))
        application.add_handler(CallbackQueryHandler(template_love, pattern="^template_love$"))
        application.add_handler(CallbackQueryHandler(template_holiday, pattern="^template_holiday$"))
        application.add_handler(CallbackQueryHandler(template_family, pattern="^template_family$"))
        application.add_handler(CallbackQueryHandler(template_memory, pattern="^template_memory$"))
        application.add_handler(CallbackQueryHandler(template_trend, pattern="^template_trend$"))
        application.add_handler(CallbackQueryHandler(template_comedy, pattern="^template_comedy$"))
        
        application.add_handler(CallbackQueryHandler(help_menu, pattern="^help_menu$"))
        application.add_handler(CallbackQueryHandler(help_how, pattern="^help_how$"))
        application.add_handler(CallbackQueryHandler(help_admin, pattern="^help_admin$"))
        application.add_handler(CallbackQueryHandler(loyalty_menu, pattern="^loyalty_menu$"))
        application.add_handler(CallbackQueryHandler(loyalty_history, pattern="^loyalty_history$"))
        application.add_handler(CallbackQueryHandler(loyalty_claim_promo, pattern="^loyalty_claim:"))
        
        application.add_handler(CallbackQueryHandler(my_stats_button, pattern="^my_stats_button$"))
        application.add_handler(CallbackQueryHandler(create_video, pattern="^create_video$"))
        application.add_handler(CallbackQueryHandler(back_to_menu, pattern="^back_to_menu$"))
        application.add_handler(CallbackQueryHandler(wait_for_photo, pattern="^wait_for_photo$"))
        
        # ADMIN CALLBACKS
        application.add_handler(CallbackQueryHandler(admin_users_list, pattern="^admin_users_list$"))
        application.add_handler(CallbackQueryHandler(admin_broadcast, pattern="^admin_broadcast$"))
        application.add_handler(CallbackQueryHandler(admin_detailed_stats, pattern="^admin_detailed_stats$"))
        application.add_handler(CallbackQueryHandler(admin_back, pattern="^admin_back$"))
        
        # Photo va text handlers
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        
        # TEXT MESSAGE HANDLERS - GROUP 0: Broadcast first (higher priority)
        # Group 0 = Broadcast handler (only admin, only when waiting)
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_broadcast_message), group=0)
        
        # Group 1 = Regular messages
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message), group=1)
        
        # Error handler
        application.add_error_handler(error_handler)
        
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("🚀 JONLANTIR AI BOT ISHGA TUSHDI!")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"👑 Adminlar: {len(ADMIN_IDS)} ta")
        print("⚡ Parallel: Bir vaqtda ko'p user")
        print("⏰ Cheklov: 6 soatda 1 video")
        print("🎭 Stsenariylar: 200+ variant")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print("🤖 @Jonlantir_Ai_bot")
        print("🔴 To'xtatish: Ctrl+C")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        
        # PARALLEL PROCESSING - Ko'p foydalanuvchilar uchun
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except KeyboardInterrupt:
        print("\n🛑 Bot to'xtatildi.")
    except Exception as e:
        logger.error(f"Bot xatolik: {e}")


if __name__ == '__main__':
    main()