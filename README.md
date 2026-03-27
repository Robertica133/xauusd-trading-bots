# XAU/USD Trading Bot - MetaTrader 5

Bot minimalist de trading XAU/USD cu confirmare manuală.

## Cum funcționează

1. Botul scanează piața XAU/USD prin MetaTrader 5 tick-by-tick
2. Când detectează un semnal, afișează:
   - `🟢 BUY la 3045.50? (da/nu):`
   - `🔴 SELL la 3045.50? (da/nu):`
3. Scrie `da` → botul plasează ordinul automat pe MT5 cu SL/TP
4. Scrie `nu` → ignoră și continuă scanarea

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

| Parametru | Valoare |
|-----------|---------|
| Lot       | 0.01    |
| SL        | 300 pips |
| TP        | 500 pips |
| Max pozitii | 3    |
| Max spread  | 50 pips |
| Cooldown    | 60 sec  |

## Indicatori utilizați

RSI (14), EMA 9/21, MACD (12,26,9), Bollinger Bands (20,2)

Semnalul necesită minim 3 din 4 indicatori în aceeași direcție.

## ⚠️ DISCLAIMER

**Doar scop educațional.** NU constituie sfat financiar.
Tranzacționarea cu leverage implică risc mare de pierdere a capitalului.
