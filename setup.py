"""
Setup script for Telegram Image to Video Bot
Bu skript botni ishga tushirishdan oldin kerakli tekshiruvlarni amalga oshiradi
"""

import os
import sys


def check_python_version():
    """Check if Python version is 3.8 or higher"""
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 yoki undan yuqori versiya kerak!")
        print(f"   Sizning versiyangiz: {sys.version}")
        return False
    print(f"✅ Python versiyasi: {sys.version_info.major}.{sys.version_info.minor}")
    return True


def check_env_file():
    """Check if .env file exists and has required variables"""
    if not os.path.exists('.env'):
        print("❌ .env fayl topilmadi!")
        print("\n📝 .env faylini yaratish:")
        print("   1. .env nomli fayl yarating")
        print("   2. Quyidagi ma'lumotlarni kiriting:\n")
        print("   TELEGRAM_BOT_TOKEN=sizning_telegram_token")
        print("   VEO3_API_KEY=sizning_veo3_key\n")
        
        # Create .env file with template
        create_env = input("❓ .env faylini hozir yaratishni xohlaysizmi? (y/n): ")
        if create_env.lower() == 'y':
            with open('.env', 'w', encoding='utf-8') as f:
                f.write("# Telegram Bot Token - @BotFather dan oling\n")
                f.write("TELEGRAM_BOT_TOKEN=\n\n")
                f.write("# Veo 3 API Key - CometAPI.com dan oling\n")
                f.write("VEO3_API_KEY=\n")
            print("✅ .env fayl yaratildi! Iltimos, tokenlarni kiriting.")
            return False
        return False
    
    # Check if variables are set
    from dotenv import load_dotenv
    load_dotenv()
    
    telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
    veo3_key = os.getenv('VEO3_API_KEY')
    
    if not telegram_token or telegram_token == '':
        print("❌ TELEGRAM_BOT_TOKEN .env faylida ko'rsatilmagan!")
        return False
    
    if not veo3_key or veo3_key == '':
        print("❌ VEO3_API_KEY .env faylida ko'rsatilmagan!")
        return False
    
    print("✅ .env fayl to'g'ri sozlangan")
    return True


def check_dependencies():
    """Check if required packages are installed"""
    try:
        import telegram
        import requests
        from dotenv import load_dotenv
        print("✅ Barcha kerakli paketlar o'rnatilgan")
        return True
    except ImportError as e:
        print(f"❌ Ba'zi paketlar o'rnatilmagan: {e}")
        print("\n📦 Paketlarni o'rnatish uchun:")
        print("   pip install -r requirements.txt")
        return False


def main():
    """Main setup function"""
    print("=" * 60)
    print("🎬 Telegram Image to Video Bot - Sozlash")
    print("=" * 60)
    print()
    
    checks = [
        ("Python versiyasi", check_python_version),
        ("Dependencies", check_dependencies),
        ("Environment variables", check_env_file)
    ]
    
    all_passed = True
    for name, check_func in checks:
        print(f"\n🔍 Tekshirilmoqda: {name}")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("✅ Barcha tekshiruvlar muvaffaqiyatli o'tdi!")
        print("🚀 Botni ishga tushirish uchun quyidagi buyruqni bajaring:")
        print("   python bot.py")
    else:
        print("❌ Ba'zi tekshiruvlar muvaffaqiyatsiz tugadi!")
        print("📋 Yuqoridagi ko'rsatmalarni bajaring va qaytadan urinib ko'ring:")
        print("   python setup.py")
    print("=" * 60)


if __name__ == '__main__':
    main()

