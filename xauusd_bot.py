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

# ═══════════════════════════════════════════
# AUTO-TRADING CONFIGURATION
# ═══════════════════════════════════════════
AUTO_TRADE_ENABLED = False     # False = confirmare manuala, True = plasare automata
CONFIRM_BEFORE_TRADE = True    # True = botul intreaba inainte de fiecare tranzactie
ASK_COOLDOWN = 30              # Secunde intre intrebari consecutive
LOT_SIZE = 0.01                # Dimensiunea lotului (0.01 = micro lot, minim pentru demo)
STOP_LOSS_PIPS = 300           # Stop Loss în pips (puncte) - ex: 300 = ~3$ pe XAUUSD
TAKE_PROFIT_PIPS = 500         # Take Profit în pips (puncte) - ex: 500 = ~5$ pe XAUUSD
MAX_OPEN_POSITIONS = 3         # Maxim poziții deschise simultan
MAGIC_NUMBER = 123456          # ID unic pentru ordinele botului
TRADE_COOLDOWN = 60            # Secunde minim între tranzacții consecutive
SYMBOL = "XAUUSD"              # Simbolul tranzacționat (suprascris după detectare)
MAX_SPREAD_PIPS = 50           # Spread maxim acceptat (pips) - nu tranzacționează dacă e mai mare

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
        # Auto-trading state
        self.last_trade_time = None       # timestamp of last executed trade
        self.last_trade_info = None       # dict with info about last trade
        # Confirmation cooldown state
        self.last_ask_time = None         # timestamp of last confirmation prompt
        self.last_no_signal = None        # last signal type user declined ("BUY"/"SELL")
        self.last_no_time = None          # timestamp when user said "no"

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

    def get_open_positions(self):
        """Returnează pozițiile deschise pentru simbol cu MAGIC_NUMBER-ul botului"""
        positions = mt5.positions_get(symbol=self.mt5.symbol)
        if positions is None:
            return []
        return [p for p in positions if p.magic == MAGIC_NUMBER]

    def execute_trade(self, signal, price, strength=0):
        """Plasează un ordin BUY sau SELL pe MT5 cu toate verificările de siguranță"""
        if not AUTO_TRADE_ENABLED and not CONFIRM_BEFORE_TRADE:
            return None

        # Verificare scor semnal > 60%
        # max_conditions matches the number of indicator checks in get_signal()
        max_conditions = 4
        score_pct = int((strength / max_conditions) * 100)
        if score_pct <= 60:
            return None

        # Verificare număr maxim de poziții deschise
        open_positions = self.get_open_positions()
        if len(open_positions) >= MAX_OPEN_POSITIONS:
            return None

        # Verificare cooldown
        now_ts = time.time()
        if self.last_trade_time is not None and (now_ts - self.last_trade_time) < TRADE_COOLDOWN:
            return None

        # Verificare spread
        spread_pts = self.mt5.get_spread_points()
        if spread_pts > MAX_SPREAD_PIPS:
            now_str = datetime.now().strftime('%H:%M:%S')
            self.history.append(
                "  [" + now_str + "] " + YELLOW + "WARNING: Spread prea mare (" + str(spread_pts) + " pips) - ordin anulat" + RESET
            )
            return None

        # Obține prețul live și informații despre simbol
        tick = mt5.symbol_info_tick(self.mt5.symbol)
        sym_info = mt5.symbol_info(self.mt5.symbol)
        if tick is None or sym_info is None:
            return None

        point = sym_info.point if sym_info.point > 0 else 0.01
        digits = sym_info.digits if sym_info.digits > 0 else 2

        if signal == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            entry = tick.ask
            sl = round(entry - STOP_LOSS_PIPS * point, digits)
            tp = round(entry + TAKE_PROFIT_PIPS * point, digits)
        elif signal == "SELL":
            order_type = mt5.ORDER_TYPE_SELL
            entry = tick.bid
            sl = round(entry + STOP_LOSS_PIPS * point, digits)
            tp = round(entry - TAKE_PROFIT_PIPS * point, digits)
        else:
            return None

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.mt5.symbol,
            "volume": LOT_SIZE,
            "type": order_type,
            "price": entry,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": "xauusd_bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        now_str = datetime.now().strftime('%H:%M:%S')

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.last_trade_time = now_ts
            self.last_trade_info = {
                "signal": signal,
                "price": entry,
                "sl": sl,
                "tp": tp,
                "time": datetime.now(),
            }
            color = GREEN if signal == "BUY" else RED
            self.history.append(
                "  [" + now_str + "] " + color + BOLD + "AUTO-TRADE: " + signal + " " + f"{LOT_SIZE:.2f}" + " " + self.mt5.symbol + " @ $" + f"{entry:.2f}" + " | SL: $" + f"{sl:.2f}" + " | TP: $" + f"{tp:.2f}" + RESET
            )
            color_label = GREEN if signal == "BUY" else RED
            print(color_label + BOLD + "  AUTO-TRADE: " + signal + " " + f"{LOT_SIZE:.2f}" + " " + self.mt5.symbol + " @ $" + f"{entry:.2f}" + " | SL: $" + f"{sl:.2f}" + " | TP: $" + f"{tp:.2f}" + RESET)
        else:
            retcode = result.retcode if result is not None else "N/A"
            comment = result.comment if result is not None else "Fara raspuns"
            self.history.append(
                "  [" + now_str + "] " + RED + "EROARE ordin " + signal + ": " + str(retcode) + " - " + str(comment) + RESET
            )

        if len(self.history) > 10:
            self.history = self.history[-10:]

        return result

    def close_position(self, position):
        """Închide o poziție specifică (trimite ordinul opus)"""
        tick = mt5.symbol_info_tick(self.mt5.symbol)
        if tick is None:
            return None

        if position.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.mt5.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": MAGIC_NUMBER,
            "comment": "xauusd_bot_close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        now_str = datetime.now().strftime('%H:%M:%S')
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            self.history.append(
                "  [" + now_str + "] " + YELLOW + "INCHIS pozitie #" + str(position.ticket) + " @ $" + f"{price:.2f}" + RESET
            )
        else:
            retcode = result.retcode if result is not None else "N/A"
            self.history.append(
                "  [" + now_str + "] " + RED + "EROARE inchidere pozitie #" + str(position.ticket) + ": " + str(retcode) + RESET
            )
        if len(self.history) > 10:
            self.history = self.history[-10:]
        return result

    def close_all_positions(self):
        """Închide toate pozițiile deschise ale botului (oprire de urgență)"""
        positions = self.get_open_positions()
        results = []
        for pos in positions:
            r = self.close_position(pos)
            results.append(r)
        return results

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
        print("  " + YELLOW + BOLD + "💰 PRET LIVE (MT5):" + RESET)
        print("     " + YELLOW + "BID:" + RESET + " " + WHITE + BOLD + "$" + f"{bid:.2f}" + RESET + price_change + "  |  " + YELLOW + "ASK:" + RESET + " " + WHITE + BOLD + "$" + f"{ask:.2f}" + RESET)
        print("     " + YELLOW + "Spread:" + RESET + " " + DIM + "$" + f"{spread_usd:.2f}" + " (" + str(spread_pts) + " pips)" + RESET)
        print("  " + YELLOW + "Ultima actualizare:" + RESET + " " + DIM + now + RESET)
        print("  " + YELLOW + "Conexiune MT5:" + RESET + "      " + GREEN + BOLD + "Conectat" + RESET)
        print("  " + YELLOW + "Simbol:" + RESET + "             " + DIM + self.mt5.symbol + RESET)
        print("  " + YELLOW + "Tick-uri:" + RESET + "           " + DIM + str(self.tick_count) + RESET)
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

        # ── TRADING MODE STATUS SECTION ──────────────────────────────────────
        print("")
        print("  " + CYAN + "==============================================" + RESET)
        if AUTO_TRADE_ENABLED:
            at_label = GREEN + BOLD + "ACTIV (automat)" + RESET
        else:
            at_label = YELLOW + BOLD + "CONFIRMARE MANUALA" + RESET
        print("  " + BOLD + "  MOD TRADING: " + at_label)

        open_pos = self.get_open_positions()
        total_pl = sum(p.profit for p in open_pos) if open_pos else 0.0
        pl_color = GREEN if total_pl >= 0 else RED
        pl_sign = "+" if total_pl >= 0 else ""
        print("  " + WHITE + "  Pozitii deschise: " + RESET + BOLD + str(len(open_pos)) + "/" + str(MAX_OPEN_POSITIONS) + RESET)
        print("  " + WHITE + "  P/L Total: " + RESET + pl_color + BOLD + pl_sign + "$" + f"{total_pl:.2f}" + RESET)

        if self.last_trade_info:
            lt = self.last_trade_info
            lt_color = GREEN if lt["signal"] == "BUY" else RED
            elapsed = int((datetime.now() - lt["time"]).total_seconds())
            if elapsed < 60:
                elapsed_str = str(elapsed) + " sec"
            else:
                elapsed_str = str(elapsed // 60) + " min"
            print("  " + WHITE + "  Ultima tranzactie: " + RESET + lt_color + BOLD + lt["signal"] + " @ $" + f"{lt['price']:.2f}" + RESET + DIM + " (acum " + elapsed_str + ")" + RESET)
        else:
            print("  " + WHITE + "  Ultima tranzactie: " + RESET + DIM + "Niciuna inca" + RESET)

        if AUTO_TRADE_ENABLED and self.last_trade_time is not None:
            elapsed_cd = time.time() - self.last_trade_time
            if elapsed_cd < TRADE_COOLDOWN:
                remaining = int(TRADE_COOLDOWN - elapsed_cd)
                cd_str = YELLOW + "Wait " + str(remaining) + "s" + RESET
            else:
                cd_str = GREEN + "READY" + RESET
        else:
            cd_str = GREEN + "READY" + RESET
        print("  " + WHITE + "  Cooldown: " + RESET + cd_str)
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

    def ask_confirmation(self, signal, tick, ind, strength):
        """Afiseaza mesajul de confirmare si asteapta raspunsul utilizatorului.
        Returneaza True daca utilizatorul confirma, False altfel."""
        now_ts = time.time()

        # Cooldown general intre intrebari (ASK_COOLDOWN secunde)
        if self.last_ask_time is not None and (now_ts - self.last_ask_time) < ASK_COOLDOWN:
            return False

        # Cooldown dupa "nu" pentru acelasi tip de semnal (60 secunde)
        if (self.last_no_signal == signal and
                self.last_no_time is not None and
                (now_ts - self.last_no_time) < 60):
            return False

        # Prețul corect de pe MT5
        if signal == "BUY":
            price_label = "Pret ASK"
            price_val = tick.ask
            sig_color = GREEN
            sig_icon = "🟢 SEMNAL BUY DETECTAT!"
        elif signal == "SELL":
            price_label = "Pret BID"
            price_val = tick.bid
            sig_color = RED
            sig_icon = "🔴 SEMNAL SELL DETECTAT!"
        else:
            return False

        rsi = ind.get('rsi', 0)
        ema_trend = "BULLISH" if ind.get('ema9', 0) > ind.get('ema21', 0) else "BEARISH"
        max_conditions = 4
        score_pct = int((strength / max_conditions) * 100)

        self.last_ask_time = now_ts

        # Afiseaza mesajul de confirmare
        print("")
        print(sig_color + BOLD + "  ═══════════════════════════════════════════════" + RESET)
        print(sig_color + BOLD + "  " + sig_icon + RESET)
        print(sig_color + "  " + price_label + ": $" + f"{price_val:.2f}" + " (exact de pe MT5)" + RESET)
        print(sig_color + "  Scor: " + str(score_pct) + "% | RSI: " + f"{rsi:.1f}" + " | Trend: " + ema_trend + RESET)
        print("")
        answer = input(sig_color + BOLD + "  Vrei sa dau " + signal + "? (da/nu): " + RESET).strip().lower()
        print(sig_color + BOLD + "  ═══════════════════════════════════════════════" + RESET)
        print("")

        if answer in ("da", "d", "y", "yes"):
            return True
        else:
            self.last_no_signal = signal
            self.last_no_time = now_ts
            return False

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
        if CONFIRM_BEFORE_TRADE and not AUTO_TRADE_ENABLED:
            print("  " + CYAN + BOLD + "  ⚙️  MOD: CONFIRMARE MANUALA" + RESET)
            print("  " + WHITE + "  Botul va cere confirmare inainte de fiecare tranzactie." + RESET)
            print("  " + WHITE + "  Nu va cumpara sau vinde nimic fara acordul tau!" + RESET)
        elif AUTO_TRADE_ENABLED:
            print("  " + YELLOW + BOLD + "  ⚙️  MOD: AUTO-TRADING ACTIV" + RESET)
            print("  " + WHITE + "  Botul va plasa ordine automat!" + RESET)
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
                            # Sistem de confirmare manuala sau auto-trading
                            if signal in ("BUY", "SELL") and strength >= 3:
                                trade_price = tick.ask if signal == "BUY" else tick.bid
                                if AUTO_TRADE_ENABLED:
                                    self.execute_trade(signal, trade_price, strength)
                                elif CONFIRM_BEFORE_TRADE:
                                    confirmed = self.ask_confirmation(signal, tick, ind, strength)
                                    if confirmed:
                                        self.execute_trade(signal, trade_price, strength)
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