@echo off
chcp 65001 >nul
title XAU/USD Trading Bot
color 0A
echo.
echo   ══════════════════════════════════════════
echo          XAU/USD TRADING BOT - Setup
echo   ══════════════════════════════════════════
echo.
echo   Se verifica Python...
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo   [EROARE] Python NU este instalat!
    echo.
    echo   Descarca Python de la:
    echo   https://www.python.org/downloads/
    echo.
    echo   IMPORTANT: Bifeaza "Add Python to PATH" la instalare!
    echo.
    pause
    exit /b
)

echo   [OK] Python gasit!
echo.
echo   Se instaleaza dependentele necesare...
echo   (poate dura 1-2 minute prima data)
echo.

pip install pandas ta MetaTrader5 --quiet --disable-pip-version-check

if %errorlevel% neq 0 (
    echo.
    echo   [EROARE] Nu s-au putut instala dependentele.
    echo   Incearca sa rulezi ca Administrator.
    echo.
    pause
    exit /b
)

echo.
echo   [OK] Totul este pregatit!
echo.
echo   Se porneste botul...
echo.

python xauusd_bot.py

if %errorlevel% neq 0 (
    echo.
    echo   [EROARE] Botul s-a oprit cu o eroare.
    echo   Verifica mesajul de mai sus.
echo.
)

pause
