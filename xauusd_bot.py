import os
import sys
import time
from datetime import datetime

try:
    import MetaTrader5 as mt5
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange
except ImportError:
    print("Se instaleaza dependentele necesare...")
    os.system("pip install pandas ta MetaTrader5 --quiet")
    import MetaTrader5 as mt5
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

# Simboluri posibile pentru XAU/USD la diferiti brokeri
XAUUSD_SYMBOLS = [
    "XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "XAUUSD.i",
    "XAUUSD.raw", "XAUUSDpro", "XAUUSD.stp", "Gold", "GOLDm",
    "GOLD.a", "GOLD.i", "XAUUSD.ecn", "XAUUSDc", "XAUUSD.",
]


class MT5Connection:
    """Gestioneaza conexiunea la MetaTrader 5 si obtine date LIVE"""

    def __init__(self):
        self.connected = False
        self.symbol = None
        self.tick = None
        self.prev_tick = None
        self.account_info = None
        self.last_tick_time = None

    def connect(self):
        """Initializeaza conexiunea la MT5"""
        if not mt5.initialize():
            return False, "Nu s-a putut conecta la MT5. Asigura-te ca terminalul este DESCHIS."

        self.account_info = mt5.account_info()
        if self.account_info is None:
            mt5.shutdown()
            return False, "Nu s-a putut obtine info cont. Logheaza-te in MT5."

        self.connected = True
        return True, "Conectat la MT5"

    def find_symbol(self):
        """Cauta simbolul XAU/USD disponibil la broker"""
        for sym in XAUUSD_SYMBOLS:
            info = mt5.symbol_info(sym)
            if info is not None:
                if not info.visible:
                    mt5.symbol_select(sym, True)
                self.symbol = sym
                return True, sym

        all_symbols = mt5.symbols_get()
        if all_symbols:
            for s in all_symbols:
                name = s.name.upper()
                if ("XAU" in name and "USD" in name) or ("GOLD" in name and "USD" in name):
                    if not s.visible:
                        mt5.symbol_select(s.name, True)
                    self.symbol = s.name
                    return True, s.name

        return False, None

    def get_tick(self):
        """Obtine tick-ul curent (Bid/Ask) - LIVE de la broker"""
        if not self.symbol:
            return None
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return None
        if tick.bid == 0 or tick.ask == 0:
            return None
        self.prev_tick = self.tick
        self.tick = tick
        self.last_tick_time = datetime.now()
        return tick

    def get_ohlc_data(self, timeframe=None, bars=200):
        """Obtine candele OHLC reale de la broker"""
        if timeframe is None:
            timeframe = mt5.TIMEFRAME_M1
        if not self.symbol:
            return None
        rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, bars)
        if rates is None or len(rates) == 0:
            return None
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        df.rename(columns={
            'open': 'Open',
            'high': 'High',
            'low': 'Low',
            'close': 'Close',
            'tick_volume': 'Volume',
        }, inplace=True)
        return df

    def get_spread_points(self):
        """Calculeaza spread-ul in puncte"""
        if self.tick is None:
            return 0
        info = mt5.symbol_info(self.symbol)
        if info is None:
            return 0
        spread = self.tick.ask - self.tick.bid
        point = info.point
        if point > 0:
            return int(spread / point)
        return 0

    def get_spread_dollars(self):
        """Spread in dolari"""
        if self.tick is None:
            return 0
        return self.tick.ask - self.tick.bid

    def disconnect(self):
        """Inchide conexiunea MT5"""
        mt5.shutdown()
        self.connected = False


class TradingBot:
    def __init__(self):
        self.mt5 = MT5Connection()
        self.position = None
        self.entry_price = 0
        self.take_profit = 0
        self.stop_loss = 0
        self.entry_time = None
        self.history = []
        self.current_price = 0
        self.pnl = 0
        self.last_indicator_calc = 0
        self.cached_indicators = None
        self.cached_signal = ("ASTEAPTA", 0, [])
        self.indicator_interval = 2
        self.tick_count = 0

    def calculate_indicators(self, df):
        """Calculeaza indicatori tehnici pe date REALE de la MT5"""
        indicators = {}
        try:
            close = df['Close']
            high = df['High']
            low = df['Low']

            rsi_ind = RSIIndicator(close=close, window=14)
            indicators['rsi'] = rsi_ind.rsi().iloc[-1]

            ema9_ind = EMAIndicator(close=close, window=9)
            ema21_ind = EMAIndicator(close=close, window=21)
            indicators['ema9'] = ema9_ind.ema_indicator().iloc[-1]
            indicators['ema21'] = ema21_ind.ema_indicator().iloc[-1]
            indicators['prev_ema9'] = ema9_ind.ema_indicator().iloc[-2]
            indicators['prev_ema21'] = ema21_ind.ema_indicator().iloc[-2]

            macd_ind = MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
            indicators['macd'] = macd_ind.macd().iloc[-1]
            indicators['macd_signal'] = macd_ind.macd_signal().iloc[-1]
            indicators['prev_macd'] = macd_ind.macd().iloc[-2]
            indicators['prev_macd_signal'] = macd_ind.macd_signal().iloc[-2]

            bb_ind = BollingerBands(close=close, window=20, window_dev=2)
            indicators['bb_upper'] = bb_ind.bollinger_hband().iloc[-1]
            indicators['bb_lower'] = bb_ind.bollinger_lband().iloc[-1]
            indicators['bb_middle'] = bb_ind.bollinger_mavg().iloc[-1]

            atr_ind = AverageTrueRange(high=high, low=low, close=close, window=14)
            indicators['atr'] = atr_ind.average_true_range().iloc[-1]

            if indicators['atr'] < 0.5:
                indicators['atr'] = max(indicators['atr'], close.iloc[-1] * 0.003)

            indicators['price'] = close.iloc[-1]
        except Exception:
            return None
        return indicators

    def get_signal(self, ind):
        """Genereaza semnal BUY/SELL/ASTEAPTA bazat pe indicatori"""
        buy_conditions = 0
        sell_conditions = 0
        buy_reasons = []
        sell_reasons = []

        if ind['rsi'] < 35:
            buy_conditions += 1
            buy_reasons.append("RSI supravandut")
        if ind['rsi'] > 65:
            sell_conditions += 1
            sell_reasons.append("RSI supracumparat")

        if ind['ema9'] > ind['ema21']:
            buy_conditions += 1
            buy_reasons.append("EMA9 > EMA21 (bullish)")
        if ind['ema9'] < ind['ema21']:
            sell_conditions += 1
            sell_reasons.append("EMA9 < EMA21 (bearish)")

        if ind['macd'] > ind['macd_signal']:
            buy_conditions += 1
            buy_reasons.append("MACD bullish")
        if ind['macd'] < ind['macd_signal']:
            sell_conditions += 1
            sell_reasons.append("MACD bearish")

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

    def update_position(self, signal, strength, price, atr):
        """Gestioneaza pozitiile deschise si inchise"""
        now = datetime.now()

        if self.position == 'BUY':
            self.pnl = price - self.entry_price
            if price >= self.take_profit:
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + GREEN + "CLOSE BUY @ $" + f"{price:.2f}" + " | TP ATINS | Profit: +$" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif price <= self.stop_loss:
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + RED + "CLOSE BUY @ $" + f"{price:.2f}" + " | SL ATINS | Pierdere: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif signal == "SELL" and strength >= 2:
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + YELLOW + "CLOSE BUY @ $" + f"{price:.2f}" + " | Semnal opus | P/L: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None

        elif self.position == 'SELL':
            self.pnl = self.entry_price - price
            if price <= self.take_profit:
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + GREEN + "CLOSE SELL @ $" + f"{price:.2f}" + " | TP ATINS | Profit: +$" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif price >= self.stop_loss:
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + RED + "CLOSE SELL @ $" + f"{price:.2f}" + " | SL ATINS | Pierdere: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif signal == "BUY" and strength >= 2:
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + YELLOW + "CLOSE SELL @ $" + f"{price:.2f}" + " | Semnal opus | P/L: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None

        if self.position is None and signal != "ASTEAPTA" and strength >= 2:
            self.position = signal
            self.entry_price = price
            self.entry_time = now
            self.pnl = 0
            if signal == "BUY":
                self.take_profit = price + atr * 2
                self.stop_loss = price - atr * 1
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + GREEN + "BUY  @ $" + f"{price:.2f}" + " -> TP: $" + f"{self.take_profit:.2f}" + " | SL: $" + f"{self.stop_loss:.2f}" + RESET)
            elif signal == "SELL":
                self.take_profit = price - atr * 2
                self.stop_loss = price + atr * 1
                self.history.append("  [" + now.strftime('%H:%M:%S') + "] " + RED + "SELL @ $" + f"{price:.2f}" + " -> TP: $" + f"{self.take_profit:.2f}" + " | SL: $" + f"{self.stop_loss:.2f}" + RESET)

        if len(self.history) > 10:
            self.history = self.history[-10:]

    def get_strength_bar(self, strength):
        filled = strength
        empty = 4 - strength
        bar = "#" * (filled * 3) + "-" * (empty * 3)
        pct = int((strength / 4) * 100)
        if strength == 2:
            label = "Moderat"
        elif strength == 3:
            label = "Puternic"
        elif strength == 4:
            label = "Foarte Puternic"
        else:
            label = "Slab"
        return bar + " " + str(pct) + "% (" + label + ")"

    def get_rsi_label(self, rsi):
        if rsi < 30:
            return GREEN + "Supravandut" + RESET
        elif rsi < 35:
            return GREEN + "Aproape supravandut" + RESET
        elif rsi > 70:
            return RED + "Supracumparat" + RESET
        elif rsi > 65:
            return RED + "Aproape supracumparat" + RESET
        else:
            return CYAN + "Neutru" + RESET

    def display(self, tick, ind, signal, strength, reasons):
        """Afiseaza interfata principala cu date LIVE de la MT5"""
        os.system('cls' if os.name == 'nt' else 'clear')

        bid = tick.bid
        ask = tick.ask
        spread_pts = self.mt5.get_spread_points()
        spread_usd = self.mt5.get_spread_dollars()
        now = datetime.now().strftime('%H:%M:%S.') + f"{datetime.now().microsecond // 1000:03d}"

        price_change = ""
        if self.mt5.prev_tick and self.mt5.prev_tick.bid != bid:
            diff = bid - self.mt5.prev_tick.bid
            if diff > 0:
                price_change = " " + GREEN + BOLD + "^ +$" + f"{diff:.2f}" + RESET
            elif diff < 0:
                price_change = " " + RED + BOLD + "v $" + f"{diff:.2f}" + RESET

        if signal == "BUY":
            sig_color = GREEN
            sig_icon = "[BUY]"
        elif signal == "SELL":
            sig_color = RED
            sig_icon = "[SELL]"
        else:
            sig_color = WHITE
            sig_icon = "[---]"

        ema_trend = GREEN + "Bullish ^" + RESET if ind['ema9'] > ind['ema21'] else RED + "Bearish v" + RESET

        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "       XAU/USD TRADING BOT - MT5 LIVE" + RESET)
        print(CYAN + BOLD + "          REAL-TIME TICK DATA" + RESET)
        print(CYAN + BOLD + "            Leverage: 1:100" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + YELLOW + "Bid:" + RESET + "                " + WHITE + BOLD + "$" + f"{bid:.2f}" + RESET + price_change)
        print("  " + YELLOW + "Ask:" + RESET + "                " + WHITE + BOLD + "$" + f"{ask:.2f}" + RESET)
        print("  " + YELLOW + "Spread:" + RESET + "             " + DIM + str(spread_pts) + " puncte ($" + f"{spread_usd:.2f}" + ")" + RESET)
        print("  " + YELLOW + "Ultima actualizare:" + RESET + " " + DIM + now + RESET)
        print("  " + YELLOW + "Conexiune MT5:" + RESET + "      " + GREEN + BOLD + "Conectat" + RESET)
        print("  " + YELLOW + "Simbol:" + RESET + "             " + DIM + self.mt5.symbol + RESET)
        print("  " + YELLOW + "Tick-uri:" + RESET + "           " + DIM + str(self.tick_count) + RESET)
        print("")
        print("  " + CYAN + "-- INDICATORI TEHNICI (M1 real) ----------" + RESET)
        print("  " + WHITE + "RSI (14):" + RESET + "       " + BOLD + f"{ind['rsi']:.2f}" + RESET + "  [" + self.get_rsi_label(ind['rsi']) + "]")
        print("  " + WHITE + "EMA 9:" + RESET + "          " + BOLD + "$" + f"{ind['ema9']:.2f}" + RESET)
        print("  " + WHITE + "EMA 21:" + RESET + "         " + BOLD + "$" + f"{ind['ema21']:.2f}" + RESET + "  [" + ema_trend + "]")
        print("  " + WHITE + "MACD:" + RESET + "           " + BOLD + f"{ind['macd']:.4f}" + RESET + " | Signal: " + BOLD + f"{ind['macd_signal']:.4f}" + RESET)
        print("  " + WHITE + "Bollinger:" + RESET + "      Upper: " + BOLD + "$" + f"{ind['bb_upper']:.2f}" + RESET + " | Lower: " + BOLD + "$" + f"{ind['bb_lower']:.2f}" + RESET)
        print("  " + WHITE + "ATR (14):" + RESET + "       " + BOLD + "$" + f"{ind['atr']:.2f}" + RESET)
        print("")
        print("  " + CYAN + "-- SEMNAL ACTUAL -------------------------" + RESET)
        print("  " + sig_color + BOLD + "  " + sig_icon + " RECOMANDARE: " + signal + RESET)

        if signal != "ASTEAPTA":
            atr = ind['atr']
            if signal == "BUY":
                print("  " + WHITE + "Take Profit:" + RESET + "   " + GREEN + BOLD + "$" + f"{bid + atr * 2:.2f}" + RESET)
                print("  " + WHITE + "Stop Loss:" + RESET + "     " + RED + BOLD + "$" + f"{bid - atr:.2f}" + RESET)
            else:
                print("  " + WHITE + "Take Profit:" + RESET + "   " + GREEN + BOLD + "$" + f"{bid - atr * 2:.2f}" + RESET)
                print("  " + WHITE + "Stop Loss:" + RESET + "     " + RED + BOLD + "$" + f"{bid + atr:.2f}" + RESET)
            print("  " + WHITE + "Putere Semnal:" + RESET + "  " + self.get_strength_bar(strength))
            if reasons:
                print("  " + DIM + "   Motive: " + ", ".join(reasons) + RESET)
        else:
            print("  " + DIM + "   Niciun semnal clar. Se asteapta confirmari..." + RESET)

        print("")
        print("  " + CYAN + "-- POZITIE DESCHISA ----------------------" + RESET)
        if self.position:
            pos_color = GREEN if self.position == "BUY" else RED
            pnl_color = GREEN if self.pnl >= 0 else RED
            pnl_sign = "+" if self.pnl >= 0 else ""
            mins = int((datetime.now() - self.entry_time).total_seconds() / 60) if self.entry_time else 0
            print("  " + WHITE + "Tip:" + RESET + "              " + pos_color + BOLD + self.position + " @ $" + f"{self.entry_price:.2f}" + RESET)
            print("  " + WHITE + "Take Profit:" + RESET + "      " + GREEN + "$" + f"{self.take_profit:.2f}" + RESET)
            print("  " + WHITE + "Stop Loss:" + RESET + "        " + RED + "$" + f"{self.stop_loss:.2f}" + RESET)
            print("  " + WHITE + "Profit/Pierdere:" + RESET + "  " + pnl_color + BOLD + pnl_sign + "$" + f"{self.pnl:.2f}" + RESET)
            print("  " + WHITE + "Deschisa de:" + RESET + "      " + str(mins) + " min")
        else:
            print("  " + DIM + "   Nicio pozitie deschisa" + RESET)

        print("")
        print("  " + CYAN + "-- ISTORIC SEMNALE -----------------------" + RESET)
        if self.history:
            for h in self.history[-10:]:
                print(h)
        else:
            print("  " + DIM + "   Niciun semnal inca..." + RESET)

        print("")
        print("  " + CYAN + "==============================================" + RESET)
        print("  " + RED + BOLD + "ATENTIE: Leverage 1:100 = RISC FOARTE MARE!" + RESET)
        print("  " + YELLOW + "   Acest bot este DOAR informativ/educational!" + RESET)
        print("  " + YELLOW + "   NU garanteaza profit. Tranzactioneaza responsabil." + RESET)
        print("  " + DIM + "   Apasa Ctrl+C pentru a opri botul." + RESET)
        print("  " + DIM + "   Se actualizeaza LIVE la fiecare ~100ms..." + RESET)

    def display_connecting(self, message=""):
        """Ecran de conectare"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "       XAU/USD TRADING BOT - MT5 LIVE" + RESET)
        print(CYAN + BOLD + "          REAL-TIME TICK DATA" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + YELLOW + "Se conecteaza la MetaTrader 5..." + RESET)
        if message:
            print("  " + DIM + message + RESET)
        print("")

    def display_error(self, error):
        """Ecran de eroare"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "       XAU/USD TRADING BOT - MT5 LIVE" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + RED + BOLD + "EROARE: " + error + RESET)
        print("")
        print("  " + YELLOW + "Solutii posibile:" + RESET)
        print("  " + WHITE + "  1. Deschide MetaTrader 5 si logheaza-te" + RESET)
        print("  " + WHITE + "  2. Asigura-te ca XAUUSD e in Market Watch" + RESET)
        print("  " + WHITE + "  3. Verifica conexiunea la internet" + RESET)
        print("  " + WHITE + "  4. Ruleaza: pip install MetaTrader5" + RESET)
        print("")
        print("  " + DIM + "Apasa ENTER pentru a reincerca sau Ctrl+C pentru iesire..." + RESET)

    def run(self):
        """Loop-ul principal al botului"""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "       XAU/USD TRADING BOT - MT5 LIVE" + RESET)
        print(CYAN + BOLD + "          REAL-TIME TICK DATA" + RESET)
        print(CYAN + BOLD + "            Leverage: 1:100" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")

        self.display_connecting("Initializare MetaTrader 5...")
        success, msg = self.mt5.connect()
        if not success:
            self.display_error(msg)
            input()
            return

        acc = self.mt5.account_info
        print("  " + GREEN + "Conectat la MT5!" + RESET)
        print("  " + WHITE + "  Server:  " + RESET + DIM + str(acc.server) + RESET)
        print("  " + WHITE + "  Login:   " + RESET + DIM + str(acc.login) + RESET)
        print("  " + WHITE + "  Balanta: " + RESET + DIM + "$" + f"{acc.balance:.2f}" + RESET)
        print("")

        print("  " + YELLOW + "Se cauta simbolul XAU/USD..." + RESET)
        found, sym = self.mt5.find_symbol()
        if not found:
            self.display_error("Nu s-a gasit XAUUSD! Adauga-l in Market Watch in MT5.")
            input()
            self.mt5.disconnect()
            return

        print("  " + GREEN + "Simbol gasit: " + sym + RESET)
        print("")
        print("  " + YELLOW + "Se porneste feed-ul LIVE..." + RESET)
        time.sleep(1)

        while True:
            try:
                tick = self.mt5.get_tick()
                if tick is None:
                    time.sleep(0.1)
                    continue

                self.tick_count += 1
                current_time = time.time()

                if current_time - self.last_indicator_calc >= self.indicator_interval:
                    df = self.mt5.get_ohlc_data(mt5.TIMEFRAME_M1, 200)
                    if df is not None and len(df) >= 30:
                        ind = self.calculate_indicators(df)
                        if ind is not None:
                            ind['price'] = tick.bid
                            self.cached_indicators = ind
                            signal, strength, reasons = self.get_signal(ind)
                            self.cached_signal = (signal, strength, reasons)
                            self.update_position(signal, strength, tick.bid, ind['atr'])
                    self.last_indicator_calc = current_time

                if self.cached_indicators is not None:
                    display_ind = dict(self.cached_indicators)
                    display_ind['price'] = tick.bid
                    signal, strength, reasons = self.cached_signal
                    self.display(tick, display_ind, signal, strength, reasons)
                else:
                    self.display_connecting(
                        "Se incarca datele OHLC...\n"
                        "  Pret LIVE: $" + f"{tick.bid:.2f}" + " / $" + f"{tick.ask:.2f}"
                    )

                time.sleep(0.1)

            except KeyboardInterrupt:
                print("")
                print("")
                print("  " + YELLOW + "Bot oprit de utilizator. La revedere!" + RESET)
                print("")
                self.mt5.disconnect()
                sys.exit(0)
            except Exception as e:
                print("")
                print("  " + RED + "Eroare: " + str(e) + RESET)
                print("  " + DIM + "Se reincearca in 3 secunde..." + RESET)
                time.sleep(3)


if __name__ == '__main__':
    print(CYAN + BOLD)
    print("  ================================================")
    print("       DISCLAIMER / AVERTISMENT IMPORTANT")
    print("  ================================================" + RESET)
    print("  " + YELLOW + "Acest bot este DOAR in scop educational/informativ." + RESET)
    print("  " + YELLOW + "NU constituie sfat financiar sau de investitii." + RESET)
    print("  " + YELLOW + "Tranzactionarea cu leverage 1:100 implica" + RESET)
    print("  " + YELLOW + "RISC FOARTE MARE de pierdere a capitalului." + RESET)
    print("  " + RED + BOLD + "  Foloseste-l pe propria raspundere!" + RESET)
    print("  " + CYAN + "================================================" + RESET)
    print("")
    print("  " + WHITE + "Cerinte: MetaTrader 5 DESCHIS si logat!" + RESET)
    print("  " + WHITE + "Simbol XAUUSD vizibil in Market Watch!" + RESET)
    print("")
    print("  " + WHITE + "Apasa ENTER pentru a porni botul..." + RESET)
    input()
    bot = TradingBot()
    bot.run()