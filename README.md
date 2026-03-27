# 🏆 XAU/USD Trading Signal Bot — MT5 Live

Bot de semnale trading pentru XAU/USD (Aur) cu analiza tehnica automata, conectat direct la **MetaTrader 5** pentru preturi identice cu brokerul tau.

## 🚀 Cum pornesti botul

1. **Instaleaza MetaTrader 5** de la [https://www.metatrader5.com/en/download](https://www.metatrader5.com/en/download)
2. **Deschide MetaTrader 5** si conecteaza-te la contul tau de broker
3. **Adauga XAUUSD in Market Watch** — apasa `Ctrl+M`, cauta `XAUUSD` (sau `GOLD`, `XAUUSDm` — depinde de broker) si adaug-o cu dublu click
4. **Lasa terminalul MT5 deschis** — botul are nevoie de el ca sa obtina pretul
5. **Descarca tot repository-ul** — apasa butonul verde `<> Code` apoi `Download ZIP`
6. **Dezarhiveaza** folderul pe Desktop
7. **Double-click pe `START.bat`** — dependentele se instaleaza automat
8. **Apasa ENTER** cand apare disclaimer-ul
9. **Gata!** Botul se conecteaza la MT5 si afiseaza semnale live!

## 📊 Ce indicatori foloseste

| Indicator | Ce face |
|-----------|---------|
| **RSI (14)** | Masoara daca aurul e supracumparat sau supravandut |
| **EMA 9 & 21** | Arata directia trendului (sus sau jos) |
| **MACD** | Confirma schimbarile de trend |
| **Bollinger Bands** | Arata volatilitatea si limitele pretului |
| **ATR** | Calculeaza cat de mult se misca pretul (pt Stop Loss / Take Profit) |

> Toti indicatorii sunt calculati pe **candele M1 reale** primite direct de la broker prin MT5.

## 📋 Ce iti arata botul

- **💰 Bid / Ask / Spread** — preturi identice cu ce vezi in MetaTrader 5
- **🕐 Timestamp precis** al ultimului tick (HH:MM:SS.mmm)
- **✓ Conexiune MT5** — indicator de stare a conexiunii
- **🟢 BUY** — cand sa cumperi (cu Take Profit si Stop Loss)
- **🔴 SELL** — cand sa vinzi (cu Take Profit si Stop Loss)
- **⚪ ASTEAPTA** — cand nu e niciun semnal clar
- **📊 Puterea semnalului** — cat de sigur e semnalul (Moderat/Puternic/Foarte Puternic)
- **💵 Profit/Pierdere** — cat ai castiga/pierde pe pozitia curenta
- **📜 Istoric** — ultimele 10 semnale

## ⚙️ Cerinte

- **Windows 10 sau 11** (biblioteca MetaTrader5 functioneaza doar pe Windows)
- **Python 3.8+** instalat — [https://www.python.org/downloads/](https://www.python.org/downloads/) *(bifeaza "Add Python to PATH"!)*
- **MetaTrader 5** instalat si deschis cu un cont de broker conectat
- **Simbolul XAUUSD** (sau varianta brokerului: GOLD, XAUUSDm, XAUUSD.) adaugat in Market Watch

## 🔧 Configurare manuala (optional)

Daca `START.bat` nu functioneaza, poti instala dependentele manual:

```bash
pip install pandas ta MetaTrader5
python xauusd_bot.py
```

## ❓ Rezolvare probleme

| Problema | Solutie |
|----------|---------|
| *MetaTrader 5 nu este disponibil* | Deschide terminalul MT5 inainte de a porni botul |
| *Nu s-a gasit simbolul XAUUSD* | Adauga simbolul in Market Watch (Ctrl+M in MT5); incearca si GOLD sau XAUUSDm |
| *Biblioteca MetaTrader5 nu e instalata* | Ruleaza `pip install MetaTrader5` sau `START.bat` |
| *Pretul nu se actualizeaza* | Verifica ca MT5 este conectat la broker si ca simbolul are cotatie activa |

## ⚠️ DISCLAIMER / AVERTISMENT

**Acest bot este DOAR in scop educational si informativ.**

- NU constituie sfat financiar sau de investitii
- NU garanteaza profit
- Tranzactionarea cu leverage 1:100 implica **RISC FOARTE MARE** de pierdere a capitalului
- Poti pierde **tot capitalul** investit
- Foloseste-l pe **propria raspundere**
- Consulta un specialist financiar inainte de a tranzactiona cu bani reali

## 🛑 Cum opresti botul

Apasa **Ctrl+C** in fereastra terminalului sau inchide fereastra.