import os
import time
import logging
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import requests
from dotenv import load_dotenv
import json
import base64
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from PIL import Image
import io
from google.cloud import vision

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

# Admin configuration
ADMIN_IDS = [5928372261]  # Shu ID bilan faqat Admin huquqlari

# Video creation limits (6 hours for regular users)
VIDEO_COOLDOWN_HOURS = 6
VIDEO_COOLDOWN_SECONDS = VIDEO_COOLDOWN_HOURS * 3600

# Database file
USER_DB_FILE = 'users_database.json'


# User Database Manager
class UserDatabase:
    def __init__(self, db_file):
        self.db_file = db_file
        self.data = self.load_db()
    
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
        """Add new user to database"""
        user_id_str = str(user_id)
        if user_id_str not in self.data:
            self.data[user_id_str] = {
                'user_id': user_id,
                'username': username,
                'first_name': first_name,
                'videos_created': 0,
                'last_video_time': 0,
                'join_date': time.time(),
                'total_requests': 0
            }
            self.save_db()
            logger.info(f"New user added: {user_id} - {username}")
    
    def can_create_video(self, user_id):
        """Check if user can create video (6 hour cooldown)"""
        # Admin has no limits
        if user_id in ADMIN_IDS:
            return True, 0
        
        user_id_str = str(user_id)
        if user_id_str not in self.data:
            return True, 0
        
        last_time = self.data[user_id_str].get('last_video_time', 0)
        time_passed = time.time() - last_time
        
        if time_passed >= VIDEO_COOLDOWN_SECONDS:
            return True, 0
        else:
            time_left = VIDEO_COOLDOWN_SECONDS - time_passed
            return False, time_left
    
    def record_video_creation(self, user_id):
        """Record that user created a video"""
        user_id_str = str(user_id)
        if user_id_str in self.data:
            self.data[user_id_str]['last_video_time'] = time.time()
            self.data[user_id_str]['videos_created'] += 1
            self.data[user_id_str]['total_requests'] += 1
            self.save_db()
    
    def get_user_stats(self, user_id):
        """Get user statistics"""
        user_id_str = str(user_id)
        if user_id_str in self.data:
            return self.data[user_id_str]
        return None
    
    def get_all_stats(self):
        """Get overall statistics"""
        total_users = len(self.data)
        total_videos = sum(user['videos_created'] for user in self.data.values())
        active_today = sum(1 for user in self.data.values() 
                          if time.time() - user.get('last_video_time', 0) < 86400)
        return {
            'total_users': total_users,
            'total_videos': total_videos,
            'active_today': active_today
        }


# Initialize database
user_db = UserDatabase(USER_DB_FILE)


# Rasmni tahlil qilish va mos prompt yaratish uchun yordamchi funksiya
class ImageAnalyzer:
    def __init__(self, service_account_file):
        self.service_account_file = service_account_file
        
    def analyze_image(self, image_bytes):
        """Rasmni CHUQUR tahlil qilish - odamlar, sifat, rang"""
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
            
            # Ranglarni tahlil qilish
            dominant_colors = []
            if props and props.dominant_colors:
                for color in props.dominant_colors.colors[:3]:
                    rgb = color.color
                    dominant_colors.append({
                        'r': rgb.red,
                        'g': rgb.green,
                        'b': rgb.blue,
                        'score': color.score
                    })
            
            # Rasm eski/xira ekanligini aniqlash
            is_old_photo = False
            is_low_quality = False
            
            # Agar ranglar juda kam yoki kulrang bo'lsa - eski rasm
            if dominant_colors:
                avg_saturation = sum([abs(c['r'] - c['g']) + abs(c['g'] - c['b']) for c in dominant_colors]) / len(dominant_colors) / 3
                if avg_saturation < 20:  # Juda past to'yinganlik = eski rasm
                    is_old_photo = True
            
            analysis = {
                'face_count': len(faces),
                'faces': [],
                'labels': [label.description.lower() for label in labels[:15]],
                'is_old_photo': is_old_photo,
                'is_low_quality': is_low_quality,
                'dominant_colors': dominant_colors
            }
            
            # Har bir yuzni tahlil qilish
            for face in faces:
                face_info = {
                    'joy': face.joy_likelihood.name,
                    'sorrow': face.sorrow_likelihood.name,
                    'anger': face.anger_likelihood.name,
                    'surprise': face.surprise_likelihood.name,
                    'headwear': face.headwear_likelihood.name
                }
                analysis['faces'].append(face_info)
            
            logger.info(f"📊 Chuqur tahlil: {analysis['face_count']} yuz, eski: {is_old_photo}, label: {analysis['labels'][:3]}")
            return analysis
            
        except Exception as e:
            logger.error(f"Image analysis error: {e}")
            return None
    
    def enhance_old_photo(self, image_bytes):
        """Eski/xira rasmni zamonaviy, rangli, sifatli qilish"""
        try:
            from PIL import Image, ImageEnhance, ImageFilter
            import io
            
            # Rasmni ochish
            img = Image.open(io.BytesIO(image_bytes))
            
            # Agar grayscale bo'lsa, RGB ga o'tkazish
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 1. Keskinlikni oshirish (Sharpness)
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(2.0)  # 2x keskinroq
            
            # 2. Kontrastni oshirish
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.5)  # 1.5x kontrast
            
            # 3. Rangni oshirish (Saturation)
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.8)  # 1.8x rangli
            
            # 4. Yorug'likni muvozanatlash
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.2)  # 1.2x yorug'roq
            
            # 5. Shovqinni kamaytirish
            img = img.filter(ImageFilter.SMOOTH)
            
            # Yangi rasmni bytes ga aylantirish
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=95)
            enhanced_bytes = output.getvalue()
            
            logger.info("✨ Rasm yaxshilandi: rangli, sifatli, zamonaviy holatga keltirildi")
            return enhanced_bytes
            
        except Exception as e:
            logger.error(f"Photo enhancement error: {e}")
            return image_bytes  # Xatolik bo'lsa asl rasmni qaytarish
    
    def generate_uzbek_prompt(self, analysis):
        """Rasmga mos DINAMIK o'zbek tilidagi prompt va so'zlarni yaratish"""
        if not analysis:
            return self.get_default_prompt()
        
        face_count = analysis['face_count']
        faces = analysis['faces']
        labels = analysis['labels']
        
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
            return self.get_default_prompt()
        
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
                return self.get_default_prompt()
        
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
    
    def get_default_prompt(self):
        """Agar tahlil amalga oshmasa, standart prompt - HAR XIL MAVZULAR"""
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
            "PHOTOREALISTIC person coming to life IN UZBEK LANGUAGE. Authentic human face with natural features, realistic skin texture showing pores and subtle imperfections. Genuine warm expression: gentle smile forming naturally, kind eyes with natural eye movement and blinks. Natural subtle movements: slow breath visible in chest/shoulders, gentle head tilt, natural eye gaze shift. Professional portrait lighting with soft shadows, natural color grading. CRITICAL: Perfect Uzbek lip-sync. Generate clear authentic Uzbek voice, friendly warm tone, natural speaking pace. Let them speak: '{{phrase}}'. High-quality audio with room presence. Photorealistic details: natural hair texture, realistic skin tones, micro facial expressions. Cinematic portrait quality, professional depth of field, 4K resolution, natural colors.",
            
            "HYPER-REALISTIC person becoming animated IN UZBEK LANGUAGE. Real human face with every authentic detail, natural imperfections making it believable, genuine expressions. Natural life-like movements: breathing visible, gentle blinking, subtle head movements, engaging eye contact. Beautiful natural lighting creating depth. CRITICAL: Flawless Uzbek audio synchronization. Authentic voice with natural tone, clear pronunciation, engaging delivery. They speak: '{{phrase}}'. Professional audio quality. Ultra-realistic human features, genuine expressions. Cinema-grade portrait, 4K."
        ]
        
        phrase = random.choice(uzbek_phrases)
        prompt = random.choice(prompt_styles).replace('{{phrase}}', phrase)
        
        return {
            'name': '🎬 Hayotga Keltirish',
            'prompt': prompt,
            'uzbek_text': phrase
        }


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
    """Handler for /start command"""
    user = update.effective_user
    
    # Foydalanuvchini bazaga qo'shish
    user_db.add_user(user.id, user.username, user.first_name)
    
    # Admin yoki oddiy foydalanuvchi
    is_admin = user.id in ADMIN_IDS
    admin_badge = " 👑" if is_admin else ""
    
    cheklov_text = "⏰ **Cheklov:** Har 6 soatda 1 ta video" if not is_admin else "👑 **Siz Admin:** Cheklovsiz video yaratish!"
    
    welcome_message = (
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
    
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for photo messages - PARALLEL PROCESSING"""
    user = update.effective_user
    photo = update.message.photo[-1]
    
    logger.info(f"🎬 START: User {user.id} ({user.first_name}) ishni boshladi")
    
    # Foydalanuvchini bazaga qo'shish
    user_db.add_user(user.id, user.username, user.first_name)
    
    # CHEKLOV TEKSHIRUVI (Admin uchun cheklov yo'q)
    can_create, time_left = user_db.can_create_video(user.id)
    
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
            
            # Rasmni yaxshilash
            image_bytes = analyzer.enhance_old_photo(image_bytes)
            logger.info(f"✨ Old photo enhanced for user {user.id}")
        
        # Rasmga mos o'zbek tilida DINAMIK prompt yaratish
        selected_style = analyzer.generate_uzbek_prompt(analysis)
        
        # DEBUG LOG
        logger.info(f"🎭 Selected scenario: {selected_style['name']}")
        logger.info(f"🗣️ Uzbek text: {selected_style.get('uzbek_text', 'N/A')[:50]}")
        
        # LOADING ANIMATSIYA - TAYYOR
        await wait_msg.edit_text(
            "┏━━━━━━━━━━━━━━━━━━━┓\n"
            "┃ ✅ **TAHLIL TUGADI** ┃\n"
            "┗━━━━━━━━━━━━━━━━━━━┛\n\n"
            f"🎭 **{selected_style['name']}**\n"
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
                user_db.record_video_creation(user.id)
                
                # Keyingi video uchun vaqtni hisoblash
                is_admin = user.id in ADMIN_IDS
                next_video_time = ""
                
                if not is_admin:
                    next_video_time = f"\n\n⏰ **Keyingi video:** {VIDEO_COOLDOWN_HOURS} soatdan keyin"
                
                # CHIROYLI CAPTION BOT LINKI BILAN
                caption = (
                    "╔═══════════════════╗\n"
                    "║ 🎬 **VIDEO TAYYOR!** ║\n"
                    "╚═══════════════════╝\n\n"
                    "✅ *Muvaffaqiyatli yaratildi*"
                    f"{next_video_time}\n\n"
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
    """Admin panel - faqat adminlar uchun"""
    user = update.effective_user
    
    # Admin emasligini tekshirish
    if user.id not in ADMIN_IDS:
        await update.message.reply_text(
            "❌ **Ruxsat yo'q!**\n\n"
            "Bu buyruq faqat adminlar uchun.",
            parse_mode='Markdown'
        )
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
    
    await update.message.reply_text(admin_text, parse_mode='Markdown')


async def my_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Foydalanuvchi o'z statistikasini ko'radi"""
    user = update.effective_user
    
    user_db.add_user(user.id, user.username, user.first_name)
    stats = user_db.get_user_stats(user.id)
    
    if not stats:
        await update.message.reply_text("Ma'lumot topilmadi.")
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
    
    stats_text = (
        "┏━━━━━━━━━━━━━━━━━┓\n"
        "┃ 📊 **STATISTIKA** ┃\n"
        "┗━━━━━━━━━━━━━━━━━┛\n\n"
        
        f"👤 {stats['first_name']}\n"
        f"🏅 {status}\n\n"
        
        f"🎬 Videolar: **{stats['videos_created']}**\n"
        f"{next_video}\n\n"
        
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━"
    )
    
    await update.message.reply_text(stats_text, parse_mode='Markdown')


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
    """Handler for text messages"""
    await update.message.reply_text(
        "📸 **Rasm yuboring**\n\n"
        "🤖 AI uni jonli videoga aylantiradi\n\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 @Jonlantir_Ai_bot\n"
        "━━━━━━━━━━━━━━━━━━",
        parse_mode='Markdown'
    )


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
        application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
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