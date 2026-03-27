@echo off
chcp 65001 >nul
title XAU/USD Auto-Trader

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python nu este instalat. Descarca de la https://www.python.org/downloads/
    pause
    exit /b
)

pip install pandas ta MetaTrader5 --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo Eroare la instalarea dependentelor.
    pause
    exit /b
)
python xauusd_bot.py
pause
