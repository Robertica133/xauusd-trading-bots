# 🥇 XAU/USD Trading Bot - MetaTrader 5 LIVE

Bot de semnale trading XAU/USD cu preț **LIVE** direct de la brokerul tău prin MetaTrader 5.

## ✨ Caracteristici

- 🔴 **Preț LIVE de la broker** - Bid/Ask identic cu MetaTrader 5
- ⚡ **Actualizare la ~100ms** - tick-by-tick, aproape instant
- 📊 **Indicatori tehnici pe date REALE** (candele M1 de la broker):
  - RSI (14)
  - EMA 9 / EMA 21
  - MACD (12, 26, 9)
  - Bollinger Bands (20, 2)
  - ATR (14)
- 🎯 **Semnale BUY / SELL / ASTEAPTA** cu putere și motive
- 📈 Spread live, info cont, istoric semnale
- ⚠️ Disclaimer și avertisment risc

## 📋 Cerințe

- **Windows** (biblioteca MT5 funcționează doar pe Windows)
- **MetaTrader 5** instalat și deschis
- **Python 3.8+**
- Cont activ la un broker cu simbol XAU/USD (sau GOLD)

## 🚀 Instalare

```bash
git clone https://github.com/Robertica133/xauusd-trading-bots.git
cd xauusd-trading-bots
pip install -r requirements.txt
```

## ▶️ Pornire

1. **Deschide MetaTrader 5** și logează-te la broker
2. **Asigură-te că XAUUSD** (sau GOLD) este vizibil în Market Watch
3. Rulează botul:

```bash
python xauusd_bot.py
```

Sau dublu-click pe `START.bat`

## ⚙️ Configurare MT5

Dacă simbolul nu este găsit automat:

1. În MT5, click dreapta în **Market Watch**
2. Alege **Show All** sau **Symbols**
3. Caută **XAUUSD** sau **GOLD**
4. Adaugă-l și repornește botul

Botul caută automat printre variantele: `XAUUSD`, `GOLD`, `XAUUSDm`, `XAUUSD.a`, `XAUUSD.i`, `XAUUSD.raw`, `XAUUSDpro`

## ⚠️ DISCLAIMER

**Acest bot este DOAR în scop educațional/informativ.**
- NU constituie sfat financiar sau de investiții
- Tranzacționarea cu leverage 1:100 implică **RISC FOARTE MARE** de pierdere a capitalului
- Folosește-l pe propria răspundere!