@echo off
chcp 65001 > nul
echo ================================
echo 🎬 Telegram Image to Video Bot
echo ================================
echo.

REM Check if virtual environment exists
if not exist "venv" (
    echo 📦 Virtual environment yaratilmoqda...
    python -m venv venv
    echo ✅ Virtual environment yaratildi!
    echo.
)

REM Activate virtual environment
echo 🔌 Virtual environment aktivlashtirilmoqda...
call venv\Scripts\activate.bat

REM Check if requirements are installed
echo 📦 Dependencies tekshirilmoqda...
pip show python-telegram-bot >nul 2>&1
if errorlevel 1 (
    echo 📥 Dependencies o'rnatilmoqda...
    pip install -r requirements.txt
    echo ✅ Dependencies o'rnatildi!
) else (
    echo ✅ Dependencies o'rnatilgan!
)
echo.

REM Check setup
echo 🔍 Sozlamalar tekshirilmoqda...
python setup.py
echo.

REM Prompt to start bot
echo ================================
set /p start="Botni ishga tushirishni xohlaysizmi? (y/n): "
if /i "%start%"=="y" (
    echo.
    echo 🚀 Bot ishga tushmoqda...
    python bot.py
) else (
    echo.
    echo 📝 Sozlamalarni to'ldirgandan keyin quyidagini bajaring:
    echo    start.bat
)

pause

