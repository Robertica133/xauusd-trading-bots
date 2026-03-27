import os
import sys
import time
from datetime import datetime

try:
    import requests
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange
except ImportError:
    print("Se instaleaza dependentele necesare...")
    os.system("pip install pandas ta requests --quiet")
    import requests
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


class LivePriceFetcher:
    """Fetches LIVE XAU/USD price from multiple free API sources (no API key needed)"""

    def __init__(self):
        self.price = 0
        self.prev_price = 0
        self.prices_history = []
        self.last_update = None
        self.source = ""
        self.errors = []

    def fetch_source_1(self):
        """Source 1: GiaVang.now - real-time XAU/USD, no key needed"""
        try:
            url = "https://giavang.now/api/prices?type=XAUUSD"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('success') and 'data' in data and len(data['data']) > 0:
                    item = data['data'][0]
                    price = float(item.get('buy', 0) or item.get('sell', 0))
                    if price > 1000:
                        return price, "GiaVang.now"
        except Exception as e:
            self.errors.append(f"GiaVang: {e}")
        return None, None

    def fetch_source_2(self):
        """Source 2: GoldPrice.org data feed - real-time"""
        try:
            url = "https://data-asg.goldprice.org/dbXRates/USD"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
                'Referer': 'https://goldprice.org/',
            }
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if 'items' in data and len(data['items']) > 0:
                    gold_price = data['items'][0].get('xauPrice', 0)
                    if gold_price and float(gold_price) > 1000:
                        return float(gold_price), "GoldPrice.org"
        except Exception as e:
            self.errors.append(f"GoldPrice: {e}")
        return None, None

    def fetch_source_3(self):
        """Source 3: Metals.live API - spot gold"""
        try:
            url = "https://api.metals.live/v1/spot/gold"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    price = float(data[0].get('price', 0))
                    if price > 1000:
                        return price, "Metals.live"
        except Exception as e:
            self.errors.append(f"Metals.live: {e}")
        return None, None

    def fetch_source_4(self):
        """Source 4: FreeGoldAPI.com - daily gold price, no key"""
        try:
            url = "https://freegoldapi.com/data/latest.json"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    latest = data[-1]
                    price = float(latest.get('price', 0))
                    if price > 1000:
                        return price, "FreeGoldAPI"
                elif isinstance(data, dict) and 'price' in data:
                    price = float(data['price'])
                    if price > 1000:
                        return price, "FreeGoldAPI"
        except Exception as e:
            self.errors.append(f"FreeGoldAPI: {e}")
        return None, None

    def fetch_source_5(self):
        """Source 5: Frankfurter API - daily XAU/USD rate"""
        try:
            url = "https://api.frankfurter.app/latest?from=XAU&to=USD"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if 'rates' in data and 'USD' in data['rates']:
                    price = float(data['rates']['USD'])
                    if price > 1000:
                        return price, "Frankfurter"
        except Exception as e:
            self.errors.append(f"Frankfurter: {e}")
        return None, None

    def fetch_source_6(self):
        """Source 6: Exchange Rate API - XAU base"""
        try:
            url = "https://open.er-api.com/v6/latest/XAU"
            resp = requests.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                if 'rates' in data and 'USD' in data['rates']:
                    price = float(data['rates']['USD'])
                    if price > 1000:
                        return price, "ExchangeRate-API"
        except Exception as e:
            self.errors.append(f"ER-API: {e}")
        return None, None

    def get_live_price(self):
        """Try all sources in order until one works"""
        self.errors = []
        sources = [
            self.fetch_source_1,
            self.fetch_source_2,
            self.fetch_source_3,
            self.fetch_source_4,
            self.fetch_source_5,
            self.fetch_source_6,
        ]
        for source_func in sources:
            price, source_name = source_func()
            if price and price > 1000:
                self.prev_price = self.price if self.price > 0 else price
                self.price = price
                self.source = source_name
                self.last_update = datetime.now()
                variation = max(abs(price - self.prev_price), 0.50)
                self.prices_history.append({
                    'time': datetime.now(),
                    'Close': price,
                    'High': price + variation * 0.3,
                    'Low': price - variation * 0.3,
                    'Open': self.prev_price if self.prev_price > 0 else price,
                })
                if len(self.prices_history) > 300:
                    self.prices_history = self.prices_history[-300:]
                return price
        return None

    def get_dataframe(self):
        """Convert collected price history to a pandas DataFrame"""
        if len(self.prices_history) < 30:
            return None
        df = pd.DataFrame(self.prices_history)
        df.set_index('time', inplace=True)
        return df

    def get_error_log(self):
        return self.errors


class TradingBot:
    def __init__(self):
        self.position = None
        self.entry_price = 0
        self.take_profit = 0
        self.stop_loss = 0
        self.entry_time = None
        self.history = []
        self.current_price = 0
        self.pnl = 0
        self.fetcher = LivePriceFetcher()
        self.warmup_done = False
        self.tick_count = 0

    def calculate_indicators(self, df):
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

            if indicators['atr'] < 1.0:
                indicators['atr'] = max(indicators['atr'], close.iloc[-1] * 0.005)

            indicators['price'] = close.iloc[-1]
        except Exception:
            return None
        return indicators

    def get_signal(self, ind):
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

    def update_position(self, signal, strength, ind):
        price = ind['price']
        atr = ind['atr']
        now = datetime.now()

        if self.position == 'BUY':
            self.pnl = price - self.entry_price
            if price >= self.take_profit:
                self.history.append("  [" + now.strftime('%H:%M') + "] " + GREEN + "CLOSE BUY @ $" + f"{price:.2f}" + " | TP ATINS | Profit: +$" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif price <= self.stop_loss:
                self.history.append("  [" + now.strftime('%H:%M') + "] " + RED + "CLOSE BUY @ $" + f"{price:.2f}" + " | SL ATINS | Pierdere: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif signal == "SELL" and strength >= 2:
                self.history.append("  [" + now.strftime('%H:%M') + "] " + YELLOW + "CLOSE BUY @ $" + f"{price:.2f}" + " | Semnal opus | P/L: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None

        elif self.position == 'SELL':
            self.pnl = self.entry_price - price
            if price <= self.take_profit:
                self.history.append("  [" + now.strftime('%H:%M') + "] " + GREEN + "CLOSE SELL @ $" + f"{price:.2f}" + " | TP ATINS | Profit: +$" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif price >= self.stop_loss:
                self.history.append("  [" + now.strftime('%H:%M') + "] " + RED + "CLOSE SELL @ $" + f"{price:.2f}" + " | SL ATINS | Pierdere: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None
                return
            elif signal == "BUY" and strength >= 2:
                self.history.append("  [" + now.strftime('%H:%M') + "] " + YELLOW + "CLOSE SELL @ $" + f"{price:.2f}" + " | Semnal opus | P/L: $" + f"{self.pnl:.2f}" + RESET)
                self.position = None

        if self.position is None and signal != "ASTEAPTA" and strength >= 2:
            self.position = signal
            self.entry_price = price
            self.entry_time = now
            self.pnl = 0
            if signal == "BUY":
                self.take_profit = price + atr * 2
                self.stop_loss = price - atr * 1
                self.history.append("  [" + now.strftime('%H:%M') + "] " + GREEN + "BUY  @ $" + f"{price:.2f}" + " -> TP: $" + f"{self.take_profit:.2f}" + " | SL: $" + f"{self.stop_loss:.2f}" + RESET)
            elif signal == "SELL":
                self.take_profit = price - atr * 2
                self.stop_loss = price + atr * 1
                self.history.append("  [" + now.strftime('%H:%M') + "] " + RED + "SELL @ $" + f"{price:.2f}" + " -> TP: $" + f"{self.take_profit:.2f}" + " | SL: $" + f"{self.stop_loss:.2f}" + RESET)

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

    def display(self, ind, signal, strength, reasons):
        os.system('cls' if os.name == 'nt' else 'clear')
        price = ind['price']
        now = datetime.now().strftime('%H:%M:%S')

        price_change = ""
        if self.fetcher.prev_price > 0 and self.fetcher.prev_price != price:
            diff = price - self.fetcher.prev_price
            if diff > 0:
                price_change = " " + GREEN + "^ +$" + f"{diff:.2f}" + RESET
            elif diff < 0:
                price_change = " " + RED + "v $" + f"{diff:.2f}" + RESET

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
        print(CYAN + BOLD + "         XAU/USD TRADING BOT" + RESET)
        print(CYAN + BOLD + "           LIVE PRICE FEED" + RESET)
        print(CYAN + BOLD + "              Leverage: 1:100" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + YELLOW + "Pret LIVE:" + RESET + "          " + WHITE + BOLD + "$" + f"{price:.2f}" + RESET + price_change)
        print("  " + YELLOW + "Ultima actualizare:" + RESET + " " + DIM + now + RESET)
        print("  " + YELLOW + "Sursa date:" + RESET + "         " + DIM + self.fetcher.source + RESET)
        print("  " + YELLOW + "Tick-uri colectate:" + RESET + " " + DIM + str(len(self.fetcher.prices_history)) + RESET)
        print("")
        print("  " + CYAN + "-- INDICATORI TEHNICI ----------------" + RESET)
        print("  " + WHITE + "RSI (14):" + RESET + "       " + BOLD + f"{ind['rsi']:.2f}" + RESET + "  [" + self.get_rsi_label(ind['rsi']) + "]")
        print("  " + WHITE + "EMA 9:" + RESET + "          " + BOLD + "$" + f"{ind['ema9']:.2f}" + RESET)
        print("  " + WHITE + "EMA 21:" + RESET + "         " + BOLD + "$" + f"{ind['ema21']:.2f}" + RESET + "  [" + ema_trend + "]")
        print("  " + WHITE + "MACD:" + RESET + "           " + BOLD + f"{ind['macd']:.4f}" + RESET + " | Signal: " + BOLD + f"{ind['macd_signal']:.4f}" + RESET)
        print("  " + WHITE + "Bollinger:" + RESET + "      Upper: " + BOLD + "$" + f"{ind['bb_upper']:.2f}" + RESET + " | Lower: " + BOLD + "$" + f"{ind['bb_lower']:.2f}" + RESET)
        print("  " + WHITE + "ATR (14):" + RESET + "       " + BOLD + "$" + f"{ind['atr']:.2f}" + RESET)
        print("")
        print("  " + CYAN + "-- SEMNAL ACTUAL -------------------------")
        print("  " + sig_color + BOLD + "  " + sig_icon + " RECOMANDARE: " + signal + RESET)

        if signal != "ASTEAPTA":
            if signal == "BUY":
                print("  " + WHITE + "Take Profit:" + RESET + "   " + GREEN + BOLD + "$" + f"{ind['price'] + ind['atr'] * 2:.2f}" + RESET)
                print("  " + WHITE + "Stop Loss:" + RESET + "     " + RED + BOLD + "$" + f"{ind['price'] - ind['atr']:.2f}" + RESET)
            else:
                print("  " + WHITE + "Take Profit:" + RESET + "   " + GREEN + BOLD + "$" + f"{ind['price'] - ind['atr'] * 2:.2f}" + RESET)
                print("  " + WHITE + "Stop Loss:" + RESET + "     " + RED + BOLD + "$" + f"{ind['price'] + ind['atr']:.2f}" + RESET)
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
            pnl_sign = "+" if self.pnl >= 0 else "-"
            mins = int((datetime.now() - self.entry_time).total_seconds() / 60) if self.entry_time else 0
            print("  " + WHITE + "Tip:" + RESET + "              " + pos_color + BOLD + self.position + " @ $" + f"{self.entry_price:.2f}" + RESET)
            print("  " + WHITE + "Take Profit:" + RESET + "      " + GREEN + "$" + f"{self.take_profit:.2f}" + RESET)
            print("  " + WHITE + "Stop Loss:" + RESET + "        " + RED + "$" + f"{self.stop_loss:.2f}" + RESET)
            print("  " + WHITE + "Profit/Pierdere:" + RESET + "  " + pnl_color + BOLD + pnl_sign + "$" + f"{self.pnl:.2f}" + RESET)
            print("  " + WHITE + "Deschisa de:" + RESET + "     " + str(mins) + " min")
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
        print("  " + DIM + "   Se actualizeaza la fiecare 10 secunde (LIVE)..." + RESET)

    def display_warmup(self, count, needed):
        os.system('cls' if os.name == 'nt' else 'clear')
        price_str = "$" + f"{self.fetcher.price:.2f}" if self.fetcher.price > 0 else "Se incarca..."
        pct = int((count / needed) * 100)
        bar_filled = int(pct / 5)
        bar = "#" * bar_filled + "-" * (20 - bar_filled)

        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "         XAU/USD TRADING BOT" + RESET)
        print(CYAN + BOLD + "           LIVE PRICE FEED" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + YELLOW + "Se colecteaza date LIVE pentru indicatori..." + RESET)
        print("")
        print("  " + WHITE + "Pret curent:" + RESET + "  " + BOLD + price_str + RESET)
        print("  " + WHITE + "Sursa:" + RESET + "        " + DIM + (self.fetcher.source if self.fetcher.source else "Se cauta...") + RESET)
        print("  " + WHITE + "Progres:" + RESET + "      [" + bar + "] " + str(pct) + "%")
        print("  " + WHITE + "Tick-uri:" + RESET + "     " + str(count) + "/" + str(needed))
        print("")
        print("  " + DIM + "Se colecteaza minimum " + str(needed) + " puncte de pret" + RESET)
        print("  " + DIM + "pentru calculul indicatorilor tehnici..." + RESET)
        print("  " + DIM + "Timp estimat: ~" + str(max(0, (needed - count) * 10)) + " secunde" + RESET)

        if self.fetcher.errors:
            print("")
            print("  " + RED + "Erori la surse:" + RESET)
            for err in self.fetcher.errors[-3:]:
                print("  " + DIM + "  - " + str(err) + RESET)

    def display_no_price(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("")
        print("  " + RED + "Nu s-a putut obtine pretul din nicio sursa." + RESET)
        print("  " + YELLOW + "Verificati conexiunea la internet." + RESET)
        print("  " + DIM + "Se reincearca in 5 secunde..." + RESET)
        print("")
        print("  " + CYAN + "Surse incercate:" + RESET)
        print("  " + DIM + "  1. GiaVang.now (real-time)" + RESET)
        print("  " + DIM + "  2. GoldPrice.org (real-time)" + RESET)
        print("  " + DIM + "  3. Metals.live (real-time)" + RESET)
        print("  " + DIM + "  4. FreeGoldAPI.com (daily)" + RESET)
        print("  " + DIM + "  5. Frankfurter API (daily)" + RESET)
        print("  " + DIM + "  6. ExchangeRate-API (daily)" + RESET)

        if self.fetcher.errors:
            print("")
            print("  " + YELLOW + "Erori de la surse:" + RESET)
            for err in self.fetcher.errors:
                print("  " + DIM + "  - " + str(err) + RESET)

    def run(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "         XAU/USD TRADING BOT" + RESET)
        print(CYAN + BOLD + "           LIVE PRICE FEED" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + YELLOW + "Se conecteaza la sursele de date LIVE..." + RESET)
        print("  " + DIM + "Se incearca 6 surse gratuite diferite." + RESET)
        print("  " + DIM + "Asteapta cateva secunde." + RESET)
        print("")

        MIN_TICKS = 35

        while True:
            try:
                price = self.fetcher.get_live_price()

                if price is None:
                    self.display_no_price()
                    time.sleep(5)
                    continue

                self.tick_count = len(self.fetcher.prices_history)

                if self.tick_count < MIN_TICKS:
                    self.display_warmup(self.tick_count, MIN_TICKS)
                    time.sleep(10)
                    continue

                df = self.fetcher.get_dataframe()
                if df is None:
                    time.sleep(10)
                    continue

                ind = self.calculate_indicators(df)
                if ind is None:
                    print("")
                    print("  " + RED + "Eroare la calculul indicatorilor." + RESET)
                    print("  " + DIM + "Se reincearca in 10 secunde..." + RESET)
                    time.sleep(10)
                    continue

                self.current_price = ind['price']
                signal, strength, reasons = self.get_signal(ind)
                self.update_position(signal, strength, ind)
                self.display(ind, signal, strength, reasons)

                time.sleep(10)

            except KeyboardInterrupt:
                print("")
                print("")
                print("  " + YELLOW + "Bot oprit de utilizator. La revedere!" + RESET)
                print("")
                sys.exit(0)
            except Exception as e:
                print("")
                print("  " + RED + "Eroare: " + str(e) + RESET)
                print("  " + DIM + "Se reincearca in 10 secunde..." + RESET)
                time.sleep(10)


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
    print("  " + WHITE + "Apasa ENTER pentru a porni botul..." + RESET)
    input()
    bot = TradingBot()
    bot.run()