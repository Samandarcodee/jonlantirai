#!/bin/bash

echo "================================"
echo "🎬 Telegram Image to Video Bot"
echo "================================"
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Virtual environment yaratilmoqda..."
    python3 -m venv venv
    echo "✅ Virtual environment yaratildi!"
    echo ""
fi

# Activate virtual environment
echo "🔌 Virtual environment aktivlashtirilmoqda..."
source venv/bin/activate

# Check if requirements are installed
echo "📦 Dependencies tekshirilmoqda..."
if ! pip show python-telegram-bot > /dev/null 2>&1; then
    echo "📥 Dependencies o'rnatilmoqda..."
    pip install -r requirements.txt
    echo "✅ Dependencies o'rnatildi!"
else
    echo "✅ Dependencies o'rnatilgan!"
fi
echo ""

# Check setup
echo "🔍 Sozlamalar tekshirilmoqda..."
python setup.py
echo ""

# Prompt to start bot
echo "================================"
read -p "Botni ishga tushirishni xohlaysizmi? (y/n): " start
if [ "$start" = "y" ] || [ "$start" = "Y" ]; then
    echo ""
    echo "🚀 Bot ishga tushmoqda..."
    python bot.py
else
    echo ""
    echo "📝 Sozlamalarni to'ldirgandan keyin quyidagini bajaring:"
    echo "   ./start.sh"
fi

