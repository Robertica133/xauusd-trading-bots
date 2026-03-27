import os
import sys
import time
from datetime import datetime, timedelta

try:
    import yfinance as yf
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange
except ImportError:
    print("Se instaleaza dependentele necesare...")
    os.system("pip install yfinance pandas ta requests --quiet")
    import yfinance as yf
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange

# Enable ANSI colors on Windows
os.system('')

# ANSI Color Codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
WHITE = "\033[97m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
MAGENTA = "\033[95m"

class TradingBot:
    def __init__(self):
        self.position = None  # None, 'BUY', or 'SELL'
        self.entry_price = 0
        self.take_profit = 0
        self.stop_loss = 0
        self.entry_time = None
        self.history = []
        self.current_price = 0
        self.pnl = 0

    def fetch_data(self):
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="5d", interval="15m")
            if df.empty:
                return None
            return df
        except Exception as e:
            return None

    def calculate_indicators(self, df):
        indicators = {}
        try:
            close = df['Close']
            high = df['High']
            low = df['Low']

            # RSI
            rsi_ind = RSIIndicator(close=close, window=14)
            indicators['rsi'] = rsi_ind.rsi().iloc[-1]

            # EMA 9 and EMA 21
            ema9_ind = EMAIndicator(close=close, window=9)
            ema21_ind = EMAIndicator(close=close, window=21)
            indicators['ema9'] = ema9_ind.ema_indicator().iloc[-1]
            indicators['ema21'] = ema21_ind.ema_indicator().iloc[-1]

            # Previous EMAs for crossover detection
            indicators['prev_ema9'] = ema9_ind.ema_indicator().iloc[-2]
            indicators['prev_ema21'] = ema21_ind.ema_indicator().iloc[-2]

            # MACD
            macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
            indicators['macd'] = macd_ind.macd().iloc[-1]
            indicators['macd_signal'] = macd_ind.macd_signal().iloc[-1]
            indicators['prev_macd'] = macd_ind.macd().iloc[-2]
            indicators['prev_macd_signal'] = macd_ind.macd_signal().iloc[-2]

            # Bollinger Bands
            bb_ind = BollingerBands(close=close, window=20, window_dev=2)
            indicators['bb_upper'] = bb_ind.bollinger_hband().iloc[-1]
            indicators['bb_lower'] = bb_ind.bollinger_lband().iloc[-1]
            indicators['bb_middle'] = bb_ind.bollinger_mavg().iloc[-1]

            # ATR
            atr_ind = AverageTrueRange(high=high, low=low, close=close, window=14)
            indicators['atr'] = atr_ind.average_true_range().iloc[-1]

            # Current price
            indicators['price'] = close.iloc[-1]

        except Exception as e:
            return None

        return indicators

    def get_signal(self, ind):
        buy_conditions = 0
        sell_conditions = 0
        buy_reasons = []
        sell_reasons = []

        # RSI
        if ind['rsi'] < 35:
            buy_conditions += 1
            buy_reasons.append("RSI supravandut")
        if ind['rsi'] > 65:
            sell_conditions += 1
            sell_reasons.append("RSI supracumparat")

        # EMA Crossover
        if ind['ema9'] > ind['ema21']:
            buy_conditions += 1
            buy_reasons.append("EMA9 > EMA21 (bullish)")
        if ind['ema9'] < ind['ema21']:
            sell_conditions += 1
            sell_reasons.append("EMA9 < EMA21 (bearish)")

        # MACD
        if ind['macd'] > ind['macd_signal']:
            buy_conditions += 1
            buy_reasons.append("MACD bullish")
        if ind['macd'] < ind['macd_signal']:
            sell_conditions += 1
            sell_reasons.append("MACD bearish")

        # Bollinger Bands
        bb_range = ind['bb_upper'] - ind['bb_lower']
        if bb_range > 0:
            if ind['price'] <= ind['bb_lower'] + bb_range * 0.1:
                buy_conditions += 1
                buy_reasons.append("Pret la banda inferioara Bollinger")
            if ind['price'] >= ind['bb_upper'] - bb_range * 0.1:
                sell_conditions += 1
                sell_reasons.append("Pret la banda superioara Bollinger")

        signal = "ASTEAPTA"
        strength = 0
        reasons = []

        if buy_conditions >= 2 and buy_conditions > sell_conditions:
            signal = "BUY"
            strength = buy_conditions
            reasons = buy_reasons
        elif sell_conditions >= 2 and sell_conditions > buy_conditions:
            signal = "SELL"
            strength = sell_conditions
            reasons = sell_reasons

        return signal, strength, reasons

    def update_position(self, signal, strength, ind):
        price = ind['price']
        atr = ind['atr']
        now = datetime.now()

        # Check TP/SL for open position
        if self.position == 'BUY':
            self.pnl = price - self.entry_price
            if price >= self.take_profit:
                self.history.append(f"  [{now.strftime('%H:%M')}] {GREEN}CLOSE BUY @ ${price:.2f} | TP ATINS | Profit: +${self.pnl:.2f}{RESET}")
                self.position = None
                return
            elif price <= self.stop_loss:
                self.history.append(f"  [{now.strftime('%H:%M')}] {RED}CLOSE BUY @ ${price:.2f} | SL ATINS | Pierdere: ${self.pnl:.2f}{RESET}")
                self.position = None
                return
            elif signal == "SELL" and strength >= 2:
                self.history.append(f"  [{now.strftime('%H:%M')}] {YELLOW}CLOSE BUY @ ${price:.2f} | Semnal opus | P/L: ${self.pnl:.2f}{RESET}")
                self.position = None

        elif self.position == 'SELL':
            self.pnl = self.entry_price - price
            if price <= self.take_profit:
                self.history.append(f"  [{now.strftime('%H:%M')}] {GREEN}CLOSE SELL @ ${price:.2f} | TP ATINS | Profit: +${self.pnl:.2f}{RESET}")
                self.position = None
                return
            elif price >= self.stop_loss:
                self.history.append(f"  [{now.strftime('%H:%M')}] {RED}CLOSE SELL @ ${price:.2f} | SL ATINS | Pierdere: ${self.pnl:.2f}{RESET}")
                self.position = None
                return
            elif signal == "BUY" and strength >= 2:
                self.history.append(f"  [{now.strftime('%H:%M')}] {YELLOW}CLOSE SELL @ ${price:.2f} | Semnal opus | P/L: ${self.pnl:.2f}{RESET}")
                self.position = None

        # Open new position
        if self.position is None and signal != "ASTEAPTA" and strength >= 2:
            self.position = signal
            self.entry_price = price
            self.entry_time = now
            self.pnl = 0
            if signal == "BUY":
                self.take_profit = price + atr * 2
                self.stop_loss = price - atr * 1
                self.history.append(f"  [{now.strftime('%H:%M')}] {GREEN}BUY  @ ${price:.2f} -> TP: ${self.take_profit:.2f} | SL: ${self.stop_loss:.2f}{RESET}")
            elif signal == "SELL":
                self.take_profit = price - atr * 2
                self.stop_loss = price + atr * 1
                self.history.append(f"  [{now.strftime('%H:%M')}] {RED}SELL @ ${price:.2f} -> TP: ${self.take_profit:.2f} | SL: ${self.stop_loss:.2f}{RESET}")

        # Keep only last 10
        if len(self.history) > 10:
            self.history = self.history[-10:]

    def get_strength_bar(self, strength):
        filled = strength
        empty = 4 - strength
        bar = "█" * (filled * 3) + "░" * (empty * 3)
        pct = int((strength / 4) * 100)
        if strength == 2:
            label = "Moderat"
        elif strength == 3:
            label = "Puternic"
        elif strength == 4:
            label = "Foarte Puternic"
        else:
            label = "Slab"
        return f"{bar} {pct}% ({label})"

    def get_rsi_label(self, rsi):
        if rsi < 30:
            return f"{GREEN}Supravandut{RESET}"
        elif rsi < 35:
            return f"{GREEN}Aproape supravandut{RESET}"
        elif rsi > 70:
            return f"{RED}Supracumparat{RESET}"
        elif rsi > 65:
            return f"{RED}Aproape supracumparat{RESET}"
        else:
            return f"{CYAN}Neutru{RESET}"

    def display(self, ind, signal, strength, reasons):
        os.system('cls' if os.name == 'nt' else 'clear')
        price = ind['price']
        now = datetime.now().strftime('%H:%M:%S')

        # Signal colors
        if signal == "BUY":
            sig_color = GREEN
            sig_icon = "🟢"
        elif signal == "SELL":
            sig_color = RED
            sig_icon = "🔴"
        else:
            sig_color = WHITE
            sig_icon = "⚪"

        # EMA trend
        ema_trend = f"{GREEN}Bullish ▲{RESET}" if ind['ema9'] > ind['ema21'] else f"{RED}Bearish ▼{RESET}"

        print(f"""
{CYAN}{BOLD}  ══════════════════════════════════════════════════{RESET}
{CYAN}{BOLD}         🏆  XAU/USD TRADING BOT  🏆{RESET}
{CYAN}{BOLD}              Leverage: 1:100{RESET}
{CYAN}{BOLD}  ═══════════════════���══════════════════════════════{RESET}

  {YELLOW}💰 Pret Curent:{RESET}        {WHITE}{BOLD}${price:.2f}{RESET}
  {YELLOW}🕐 Ultima actualizare:{RESET} {DIM}{now}{RESET}

  {CYAN}── INDICATORI TEHNICI ──────────────────────────{RESET}
  {WHITE}📈 RSI (14):{RESET}       {BOLD}{ind['rsi']:.2f}{RESET}  [{self.get_rsi_label(ind['rsi'])}]
  {WHITE}📈 EMA 9:{RESET}          {BOLD}${ind['ema9']:.2f}{RESET}
  {WHITE}📈 EMA 21:{RESET}         {BOLD}${ind['ema21']:.2f}{RESET}  [{ema_trend}]
  {WHITE}📈 MACD:{RESET}           {BOLD}{ind['macd']:.4f}{RESET} | Signal: {BOLD}{ind['macd_signal']:.4f}{RESET}
  {WHITE}📈 Bollinger:{RESET}      Upper: {BOLD}${ind['bb_upper']:.2f}{RESET} | Lower: {BOLD}${ind['bb_lower']:.2f}{RESET}
  {WHITE}📈 ATR (14):{RESET}       {BOLD}${ind['atr']:.2f}{RESET}

  {CYAN}── SEMNAL ACTUAL ───────────────────────────────{RESET}
  {sig_color}{BOLD}  {sig_icon} RECOMANDARE: {signal}{RESET}"""
)

        if signal != "ASTEAPTA":
            print(f"  {WHITE}🎯 Take Profit:{RESET}   {GREEN}{BOLD}${ind['price'] + ind['atr'] * 2:.2f}{RESET}" if signal == "BUY" else f"  {WHITE}🎯 Take Profit:{RESET}   {GREEN}{BOLD}${ind['price'] - ind['atr'] * 2:.2f}{RESET}")
            print(f"  {WHITE}🛑 Stop Loss:{RESET}     {RED}{BOLD}${ind['price'] - ind['atr']:.2f}{RESET}" if signal == "BUY" else f"  {WHITE}🛑 Stop Loss:{RESET}     {RED}{BOLD}${ind['price'] + ind['atr']:.2f}{RESET}")
            print(f"  {WHITE}📊 Putere Semnal:{RESET}  {self.get_strength_bar(strength)}")
            if reasons:
                print(f"  {DIM}   Motive: {', '.join(reasons)}{RESET}")
        else:
            print(f"  {DIM}   Niciun semnal clar. Se asteapta confirmari...{RESET}")

        # Position info
        print(f"\n  {CYAN}── POZITIE DESCHISA ────────────────────────────{RESET}")
        if self.position:
            pos_color = GREEN if self.position == "BUY" else RED
            pnl_color = GREEN if self.pnl >= 0 else RED
            pnl_sign = "+" if self.pnl >= 0 else ""
            mins = int((datetime.now() - self.entry_time).total_seconds() / 60) if self.entry_time else 0
            print(f"  {WHITE}📍 Tip:{RESET}              {pos_color}{BOLD}{self.position} @ ${self.entry_price:.2f}{RESET}")
            print(f"  {WHITE}🎯 Take Profit:{RESET}      {GREEN}${self.take_profit:.2f}{RESET}")
            print(f"  {WHITE}🛑 Stop Loss:{RESET}        {RED}${self.stop_loss:.2f}{RESET}")
            print(f"  {WHITE}💵 Profit/Pierdere:{RESET}  {pnl_color}{BOLD}{pnl_sign}${self.pnl:.2f}{RESET}")
            print(f"  {WHITE}⏱️  Deschisa de:{RESET}     {mins} min")
        else:
            print(f"  {DIM}   Nicio pozitie deschisa{RESET}")

        # History
        print(f"\n  {CYAN}── ISTORIC SEMNALE ─────────────────────────────{RESET}")
        if self.history:
            for h in self.history[-10:]:
                print(h)
        else:
            print(f"  {DIM}   Niciun semnal inca...{RESET}")

        print(f"\n  {CYAN}══════════════════════════════════════════════════{RESET}")
        print(f"  {RED}{BOLD}⚠️  ATENTIE: Leverage 1:100 = RISC FOARTE MARE!{RESET}")
        print(f"  {YELLOW}   Acest bot este DOAR informativ/educational!{RESET}")
        print(f"  {YELLOW}   NU garanteaza profit. Tranzactioneaza responsabil.{RESET}")
        print(f"  {DIM}   Apasa Ctrl+C pentru a opri botul.{RESET}")
        print(f"  {DIM}   Se actualizeaza la fiecare 30 secunde...{RESET}")

    def run(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"""
{CYAN}{BOLD}  ══════════════════════════════════════════════════{RESET}
{CYAN}{BOLD}         🏆  XAU/USD TRADING BOT  🏆{RESET}
{CYAN}{BOLD}  ══════════════════════════════════════════════════{RESET}

  {YELLOW}Se incarca datele... Asteapta cateva secunde.{RESET}
""")

        while True:
            try:
                df = self.fetch_data()
                if df is None or df.empty:
                    os.system('cls' if os.name == 'nt' else 'clear')
                    print(f"\n  {RED}⚠️  Nu s-au putut obtine datele.{RESET}")
                    print(f"  {YELLOW}Verificati conexiunea la internet.{RESET}")
                    print(f"  {DIM}Se reincearca in 10 secunde...{RESET}")
                    time.sleep(10)
                    continue

                ind = self.calculate_indicators(df)
                if ind is None:
                    print(f"\n  {RED}⚠️  Eroare la calculul indicatorilor.{RESET}")
                    print(f"  {DIM}Se reincearca in 10 secunde...{RESET}")
                    time.sleep(10)
                    continue

                self.current_price = ind['price']
                signal, strength, reasons = self.get_signal(ind)
                self.update_position(signal, strength, ind)
                self.display(ind, signal, strength, reasons)

                time.sleep(30)

            except KeyboardInterrupt:
                print(f"\n\n  {YELLOW}Bot oprit de utilizator. La revedere! 👋{RESET}\n")
                sys.exit(0)
            except Exception as e:
                print(f"\n  {RED}⚠️  Eroare: {e}{RESET}")
                print(f"  {DIM}Se reincearca in 10 secunde...{RESET}")
                time.sleep(10)

if __name__ == "__main__":
    print(f"{CYAN}{BOLD}")
    print(f"  ══════════════════════════════════════════════════")
    print(f"       DISCLAIMER / AVERTISMENT IMPORTANT")
    print(f"  ══════════════════════════════════════════════════{RESET}")
    print(f"  {YELLOW}Acest bot este DOAR in scop educational/informativ.{RESET}")
    print(f"  {YELLOW}NU constituie sfat financiar sau de investitii.{RESET}")
    print(f"  {YELLOW}Tranzactionarea cu leverage 1:100 implica{RESET}")
    print(f"  {YELLOW}RISC FOARTE MARE de pierdere a capitalului.{RESET}")
    print(f"  {RED}{BOLD}  Foloseste-l pe propria raspundere!{RESET}")
    print(f"  {CYAN}══════════════════════════════════════════════════{RESET}")
    print(f"\n  {WHITE}Apasa ENTER pentru a porni botul...{RESET}")
    input()
    bot = TradingBot()
    bot.run()