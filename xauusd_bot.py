import os
import sys
import time
from datetime import datetime

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

try:
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange
except ImportError:
    print("Se instaleaza dependentele necesare...")
    os.system("pip install pandas ta MetaTrader5 --quiet")
    import pandas as pd
    from ta.momentum import RSIIndicator
    from ta.trend import EMAIndicator, MACD
    from ta.volatility import BollingerBands, AverageTrueRange

# Try to import MetaTrader5 (Windows only)
MT5_AVAILABLE = False
try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    pass

# Default symbol — will be updated during initialization if a variant is found
SYMBOL = "XAUUSD"
# Candidate symbols in order of preference
SYMBOL_CANDIDATES = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD."]

# How often (seconds) to recalculate technical indicators
INDICATOR_REFRESH_SECS = 3
# How often (seconds) to refresh the 200-candle dataset from MT5
CANDLE_REFRESH_SECS = 5


class MT5DataFetcher:
    """Fetches real-time XAU/USD price and OHLC data directly from MetaTrader 5."""

    def __init__(self):
        self.bid = 0.0
        self.ask = 0.0
        self.prev_bid = 0.0
        self.spread_pts = 0       # spread in broker points (derived from symbol_info().point)
        self._point = 0.01        # default fallback; overwritten from symbol_info on connect
        self.last_tick_time = None
        self.connected = False
        self.symbol = SYMBOL
        self.candles_count = 0
        self._df = None

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def initialize(self):
        """Initialize MT5 connection and find the correct XAUUSD symbol."""
        global SYMBOL
        if not MT5_AVAILABLE:
            return False
        if not mt5.initialize():
            return False
        for candidate in SYMBOL_CANDIDATES:
            info = mt5.symbol_info(candidate)
            if info is not None:
                if not info.visible:
                    mt5.symbol_select(candidate, True)
                SYMBOL = candidate
                self.symbol = candidate
                # Use the broker's actual point size for spread calculation
                if info.point and info.point > 0:
                    self._point = info.point
                self.connected = True
                return True
        mt5.shutdown()
        return False

    def shutdown(self):
        if MT5_AVAILABLE and self.connected:
            mt5.shutdown()

    # ------------------------------------------------------------------
    # Live tick
    # ------------------------------------------------------------------

    def get_tick(self):
        """Fetch the latest Bid/Ask tick. Returns True on success."""
        if not self.connected:
            return False
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return False
        self.prev_bid = self.bid if self.bid > 0 else tick.bid
        self.bid = tick.bid
        self.ask = tick.ask
        # Spread in broker points using the symbol's actual point size
        raw_spread = round((self.ask - self.bid) / self._point)
        self.spread_pts = max(raw_spread, 0)
        self.last_tick_time = datetime.fromtimestamp(tick.time)
        return True

    # ------------------------------------------------------------------
    # OHLC candles
    # ------------------------------------------------------------------

    def update_candles(self):
        """Fetch the latest 200 M1 candles from MT5. Returns True on success."""
        if not self.connected:
            return False
        rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, 200)
        if rates is None or len(rates) < 35:
            return False
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df = df.rename(columns={
            'open': 'Open', 'high': 'High', 'low': 'Low',
            'close': 'Close', 'tick_volume': 'Volume'
        })
        df.set_index('time', inplace=True)
        self._df = df
        self.candles_count = len(df)
        return True

    def get_dataframe(self):
        return self._df


class TradingBot:
    def __init__(self):
        self.position = None
        self.entry_price = 0.0
        self.take_profit = 0.0
        self.stop_loss = 0.0
        self.entry_time = None
        self.history = []
        self.current_price = 0.0
        self.pnl = 0.0
        self.fetcher = MT5DataFetcher()
        self._last_indicator_calc = 0.0
        self._last_candle_refresh = 0.0
        self._cached_indicators = None
        self._cached_signal = ("ASTEAPTA", 0, [])

    # ------------------------------------------------------------------
    # Technical indicators
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

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
            self.pnl = 0.0
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

    # ------------------------------------------------------------------
    # Display helpers
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Main display
    # ------------------------------------------------------------------

    def display(self, ind, signal, strength, reasons):
        os.system('cls' if os.name == 'nt' else 'clear')
        bid = self.fetcher.bid
        ask = self.fetcher.ask
        spread_pts = self.fetcher.spread_pts
        spread_usd = spread_pts * self.fetcher._point

        tick_time_str = (
            self.fetcher.last_tick_time.strftime('%H:%M:%S.') +
            f"{self.fetcher.last_tick_time.microsecond // 1000:03d}"
            if self.fetcher.last_tick_time else "--:--:--.---"
        )

        price_change = ""
        if self.fetcher.prev_bid > 0 and self.fetcher.prev_bid != bid:
            diff = bid - self.fetcher.prev_bid
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

        conn_str = GREEN + "✓ Conectat" + RESET
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
        print("  " + YELLOW + "Ultima actualizare:" + RESET + " " + DIM + tick_time_str + RESET)
        print("  " + YELLOW + "Conexiune MT5:" + RESET + "      " + conn_str)
        print("  " + YELLOW + "Simbol:" + RESET + "             " + DIM + self.fetcher.symbol + RESET)
        print("  " + YELLOW + "Candele M1:" + RESET + "         " + DIM + str(self.fetcher.candles_count) + RESET)
        print("")
        print("  " + CYAN + "-- INDICATORI TEHNICI (M1 real) ----------" + RESET)
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
        print("  " + DIM + "   Se actualizeaza LIVE la fiecare 100ms..." + RESET)

    def display_no_mt5(self):
        """Shown when MT5 is not installed or not reachable."""
        os.system('cls' if os.name == 'nt' else 'clear')
        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "       XAU/USD TRADING BOT - MT5 LIVE" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + RED + BOLD + "  [!] MetaTrader 5 nu este disponibil!" + RESET)
        print("")
        if not MT5_AVAILABLE:
            print("  " + YELLOW + "Biblioteca MetaTrader5 nu este instalata." + RESET)
            print("  " + WHITE + "Instaleaza-o cu:" + RESET)
            print("  " + CYAN + "    pip install MetaTrader5" + RESET)
            print("")
            print("  " + DIM + "  Nota: MetaTrader5 functioneaza doar pe Windows." + RESET)
        else:
            print("  " + YELLOW + "Terminalul MetaTrader 5 nu este deschis" + RESET)
            print("  " + YELLOW + "sau nu s-a putut gasi simbolul XAUUSD." + RESET)
        print("")
        print("  " + CYAN + "Pasi pentru a porni botul:" + RESET)
        print("  " + WHITE + "  1. Descarca si instaleaza MetaTrader 5:" + RESET)
        print("  " + DIM + "     https://www.metatrader5.com/en/download" + RESET)
        print("  " + WHITE + "  2. Deschide MetaTrader 5 si conecteaza-te la broker." + RESET)
        print("  " + WHITE + "  3. In Market Watch (Ctrl+M) adauga XAUUSD" + RESET)
        print("  " + DIM + "     (sau GOLD, XAUUSDm — depinde de broker)." + RESET)
        print("  " + WHITE + "  4. Lasa terminalul MT5 deschis si reporneste botul." + RESET)
        print("")
        print("  " + DIM + "   Se reincearca in 10 secunde..." + RESET)

    def display_warmup(self, candles):
        """Shown while waiting for enough candles."""
        os.system('cls' if os.name == 'nt' else 'clear')
        bid = self.fetcher.bid
        price_str = "$" + f"{bid:.2f}" if bid > 0 else "Se incarca..."
        pct = int((candles / 35) * 100)
        bar_filled = int(pct / 5)
        bar = "#" * bar_filled + "-" * (20 - bar_filled)

        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "       XAU/USD TRADING BOT - MT5 LIVE" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + YELLOW + "Se colecteaza candele M1 de la MT5..." + RESET)
        print("")
        print("  " + WHITE + "Bid curent:" + RESET + "  " + BOLD + price_str + RESET)
        print("  " + WHITE + "Simbol:" + RESET + "      " + DIM + self.fetcher.symbol + RESET)
        print("  " + WHITE + "Candele:" + RESET + "     [" + bar + "] " + str(pct) + "%  (" + str(candles) + "/35)")
        print("")
        print("  " + DIM + "Se asteapta minimum 35 candele pentru indicatori..." + RESET)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("")
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print(CYAN + BOLD + "       XAU/USD TRADING BOT - MT5 LIVE" + RESET)
        print(CYAN + BOLD + "  ==============================================" + RESET)
        print("")
        print("  " + YELLOW + "Se conecteaza la MetaTrader 5..." + RESET)
        print("")

        while True:
            # (Re-)connect if needed
            if not self.fetcher.connected:
                if not self.fetcher.initialize():
                    self.display_no_mt5()
                    time.sleep(10)
                    continue

            try:
                now_ts = time.monotonic()

                # Fetch latest tick (Bid/Ask) every iteration (~100 ms)
                if not self.fetcher.get_tick():
                    self.fetcher.connected = False
                    continue

                # Refresh candles periodically
                if now_ts - self._last_candle_refresh >= CANDLE_REFRESH_SECS:
                    self.fetcher.update_candles()
                    self._last_candle_refresh = now_ts

                # Need candles to compute indicators
                df = self.fetcher.get_dataframe()
                if df is None or self.fetcher.candles_count < 35:
                    self.display_warmup(self.fetcher.candles_count)
                    time.sleep(0.1)
                    continue

                # Recalculate indicators periodically (not every tick)
                if now_ts - self._last_indicator_calc >= INDICATOR_REFRESH_SECS:
                    ind = self.calculate_indicators(df)
                    if ind is not None:
                        self._cached_indicators = ind
                        self._cached_signal = self.get_signal(ind)
                        self.update_position(self._cached_signal[0], self._cached_signal[1], ind)
                    self._last_indicator_calc = now_ts

                if self._cached_indicators is None:
                    time.sleep(0.1)
                    continue

                signal, strength, reasons = self._cached_signal
                self.display(self._cached_indicators, signal, strength, reasons)

                time.sleep(0.1)

            except KeyboardInterrupt:
                print("")
                print("")
                print("  " + YELLOW + "Bot oprit de utilizator. La revedere!" + RESET)
                print("")
                self.fetcher.shutdown()
                sys.exit(0)
            except Exception as e:
                print("")
                print("  " + RED + "Eroare: " + str(e) + RESET)
                print("  " + DIM + "Se reincearca in 5 secunde..." + RESET)
                time.sleep(5)


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