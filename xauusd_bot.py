import time
import sys
import MetaTrader5 as mt5
import pandas as pd
import ta

# ── Configurare ──────────────────────────────────────────────────────────────
LOT        = 0.01
SL_PIPS    = 300
TP_PIPS    = 500
MAX_POS    = 3
MAX_SPREAD = 50
COOLDOWN       = 60   # secunde intre tranzactii
MIN_INDICATORS = 3    # cate indicatori trebuie sa confirme semnalul (din 4)
SYMBOLS        = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "XAUUSD.i",
                  "XAUUSD.raw", "XAUUSDpro"]

last_trade = 0
symbol     = None

# ── Conexiune MT5 ─────────────────────────────────────────────────────────────
def connect():
    global symbol
    print("Conectare MT5...", end=" ", flush=True)
    if not mt5.initialize():
        print("EROARE:", mt5.last_error())
        sys.exit(1)
    print("OK")

    for s in SYMBOLS:
        info = mt5.symbol_info(s)
        if info is not None and info.visible:
            symbol = s
            break
        if info is not None:
            mt5.symbol_select(s, True)
            symbol = s
            break

    if symbol is None:
        print("Simbol XAUUSD/GOLD negasit in Market Watch.")
        mt5.shutdown()
        sys.exit(1)

    acc = mt5.account_info()
    acc_type = "Demo" if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "Real"
    print(f"Simbol: {symbol} | Cont: {acc.login} ({acc_type})")
    print("Scanare activa...\n")

# ── Numara pozitii deschise ────────────────────────────────────────────────────
def open_positions():
    pos = mt5.positions_get(symbol=symbol)
    return len(pos) if pos else 0

# ── Citeste date OHLC si calculeaza indicatori ────────────────────────────────
def get_signal():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 100)
    if rates is None or len(rates) < 50:
        return None

    df = pd.DataFrame(rates)
    df["rsi"]  = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["ema9"] = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
    df["ema21"]= ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()

    macd_obj   = ta.trend.MACD(df["close"])
    df["macd"] = macd_obj.macd()
    df["msig"] = macd_obj.macd_signal()

    bb         = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bb_lo"]= bb.bollinger_lband()
    df["bb_hi"]= bb.bollinger_hband()

    last = df.iloc[-1]
    rsi, ema9, ema21 = last["rsi"], last["ema9"], last["ema21"]
    macd, msig       = last["macd"], last["msig"]
    close            = last["close"]
    bb_lo, bb_hi     = last["bb_lo"], last["bb_hi"]

    buy_score  = 0
    sell_score = 0

    if rsi < 40:
        buy_score  += 1
    elif rsi > 60:
        sell_score += 1

    if ema9 > ema21:
        buy_score  += 1
    elif ema9 < ema21:
        sell_score += 1

    if macd > msig:
        buy_score  += 1
    elif macd < msig:
        sell_score += 1

    if close < bb_lo:
        buy_score  += 1
    elif close > bb_hi:
        sell_score += 1

    if buy_score >= MIN_INDICATORS:
        return "BUY"
    if sell_score >= MIN_INDICATORS:
        return "SELL"
    return None

# ── Plaseaza ordin ────────────────────────────────────────────────────────────
def place_order(direction, price, spread):
    sym_info = mt5.symbol_info(symbol)
    pip      = sym_info.point
    digits   = sym_info.digits

    if direction == "BUY":
        sl = price - SL_PIPS * pip
        tp = price + TP_PIPS * pip
        order_type = mt5.ORDER_TYPE_BUY
        entry = mt5.symbol_info_tick(symbol).ask
    else:
        sl = price + SL_PIPS * pip
        tp = price - TP_PIPS * pip
        order_type = mt5.ORDER_TYPE_SELL
        entry = mt5.symbol_info_tick(symbol).bid

    # Selecteaza modul de umplere suportat de broker
    filling_mode = sym_info.filling_mode
    if filling_mode & mt5.ORDER_FILLING_IOC:
        filling = mt5.ORDER_FILLING_IOC
    elif filling_mode & mt5.ORDER_FILLING_FOK:
        filling = mt5.ORDER_FILLING_FOK
    else:
        filling = mt5.ORDER_FILLING_RETURN

    req = {
        "action":        mt5.TRADE_ACTION_DEAL,
        "symbol":        symbol,
        "volume":        LOT,
        "type":          order_type,
        "price":         entry,
        "sl":            round(sl, digits),
        "tp":            round(tp, digits),
        "deviation":     20,
        "magic":         202400,
        "comment":       "xauusd_bot",
        "type_time":     mt5.ORDER_TIME_GTC,
        "type_filling":  filling,
    }

    result = mt5.order_send(req)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ {direction} executat! SL: {req['sl']:.2f} | TP: {req['tp']:.2f}\n")
        return True
    else:
        print(f"❌ Eroare ordin: {result.retcode} - {result.comment}\n")
        return False

# ── Bucla principala ──────────────────────────────────────────────────────────
def run():
    global last_trade
    connect()

    try:
        while True:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                time.sleep(1)
                continue

            price  = (tick.bid + tick.ask) / 2
            spread = round((tick.ask - tick.bid) / mt5.symbol_info(symbol).point)

            print(f"Pret: {price:.2f}", flush=True)

            now = time.time()
            cooldown_ok = (now - last_trade) >= COOLDOWN
            spread_ok   = spread <= MAX_SPREAD
            pos_ok      = open_positions() < MAX_POS

            if not spread_ok:
                print(f"  Spread prea mare ({spread} pips), astept...\n")
                time.sleep(5)
                continue

            if not cooldown_ok:
                remaining = int(COOLDOWN - (now - last_trade))
                print(f"  Cooldown {remaining}s...\n")
                time.sleep(5)
                continue

            if not pos_ok:
                print(f"  Max {MAX_POS} pozitii deschise, astept...\n")
                time.sleep(5)
                continue

            signal = get_signal()

            if signal == "BUY":
                answer = input(f"\033[92m🟢 BUY la {price:.2f}? (da/nu): \033[0m").strip().lower()
                if answer == "da":
                    if place_order("BUY", price, spread):
                        last_trade = time.time()
                else:
                    print("⏭ Ignorat.\n")

            elif signal == "SELL":
                answer = input(f"\033[91m🔴 SELL la {price:.2f}? (da/nu): \033[0m").strip().lower()
                if answer == "da":
                    if place_order("SELL", price, spread):
                        last_trade = time.time()
                else:
                    print("⏭ Ignorat.\n")

            time.sleep(2)

    except KeyboardInterrupt:
        print("\n[Ctrl+C] Bot oprit.")
        mt5.shutdown()

if __name__ == "__main__":
    run()
