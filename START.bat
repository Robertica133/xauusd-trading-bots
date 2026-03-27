@echo off
chcp 65001 >nul
title XAU/USD Trading Bot

echo Verificare Python...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [EROARE] Python nu este instalat!
    echo Descarca de la https://www.python.org/downloads/
    echo Bifeaza "Add Python to PATH" la instalare!
    pause
    exit /b
)

echo Instalare dependente...
pip install pandas ta MetaTrader5 --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo [EROARE] Nu s-au putut instala dependentele.
    echo Incearca sa rulezi ca Administrator.
    pause
    exit /b
)

echo Pornire bot...
python xauusd_bot.py

pause
