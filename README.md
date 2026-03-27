# XAU/USD Auto-Trader — MetaTrader 5

Auto-trader XAU/USD pe MT5, 50% balance, full automat.

## Cum funcționează

- Botul scanează XAU/USD prin MetaTrader 5 la fiecare 2 secunde
- Calculează automat lot-ul din 50% din balanța contului
- Când detectează semnal (RSI, EMA, MACD, Bollinger Bands) → execută imediat, fără confirmare
- Afișează doar ce face: preț, semnal, SL, TP

## Cerințe

- Windows (biblioteca MT5 funcționează doar pe Windows)
- MetaTrader 5 instalat și deschis, cu cont activ (demo sau real)
- Python 3.8+

## Instalare și pornire

```bash
pip install -r requirements.txt
python xauusd_bot.py
```

Sau dublu-click pe `START.bat`.

## Configurare

| Parametru     | Valoare  |
|---------------|----------|
| Lot           | 50% din balanță |
| SL            | 300 pips |
| TP            | 500 pips |
| Max poziții   | 3        |
| Max spread    | 50 pips  |
| Cooldown      | 60 sec   |
| Magic number  | 123456   |

## ⚠️ DISCLAIMER

**Doar scop educațional.** NU constituie sfat financiar.
Tranzacționarea cu leverage implică risc mare de pierdere a capitalului.
