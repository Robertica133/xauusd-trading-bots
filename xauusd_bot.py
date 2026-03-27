import time
import sys
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd
import ta

# ── Configurare ───────────────────────────────────────────────────────────────
SL_PIPS        = 300
TP_PIPS        = 500
MAX_POS        = 3
MAX_SPREAD     = 50
COOLDOWN       = 60
MIN_INDICATORS = 2
MAGIC          = 123456
BALANCE_PCT    = 0.50
SYMBOLS        = ["XAUUSD", "GOLD", "XAUUSDm", "XAUUSD.a", "XAUUSD.i",
                  "XAUUSD.raw", "XAUUSDpro"]

last_trade = 0
symbol     = None
lot        = 0.01

# ── Conexiune MT5 ─────────────────────────────────────────────────────────────
def connect():
    global symbol, lot
    print("Conectare MT5...", end=" ", flush=True)
    if not mt5.initialize():
        print("EROARE:", mt5.last_error())
        sys.exit(1)
    print("OK")

    for s in SYMBOLS:
        info = mt5.symbol_info(s)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(s, True)
            symbol = s
            break

    if symbol is None:
        print("Simbol XAUUSD/GOLD negasit in Market Watch.")
        mt5.shutdown()
        sys.exit(1)

    acc      = mt5.account_info()
    acc_type = "Demo" if acc.trade_mode == mt5.ACCOUNT_TRADE_MODE_DEMO else "Real"
    print(f"Cont: {acc.login} ({acc_type}) | Balanta: ${acc.balance:.2f}")

    lot = calc_lot(acc.balance)
    print(f"Simbol: {symbol} | Lot calculat: {lot:.2f} (50% din balanta)\n")

# ── Calculeaza lot dinamic (50% din balanta) ──────────────────────────────────
def calc_lot(balance):
    tick     = mt5.symbol_info_tick(symbol)
    info     = mt5.symbol_info(symbol)
    if tick is None or info is None:
        print("Avertisment: lot calcul esuat, se foloseste lot implicit 0.01")
        return 0.01
    price         = tick.ask
    contract_size = info.trade_contract_size   # e.g. 100 oz for XAUUSD
    raw           = (balance * BALANCE_PCT) / (contract_size * price)
    step          = info.volume_step
    raw           = max(info.volume_min, min(info.volume_max, raw))
    return round(round(raw / step) * step, 2)

# ── Numara pozitii deschise ────────────────────────────────────────────────────
def open_positions():
    pos = mt5.positions_get(symbol=symbol)
    return len(pos) if pos else 0

# ── Indicatori si semnal ──────────────────────────────────────────────────────
def get_signal():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 100)
    if rates is None or len(rates) < 50:
        return None

    df        = pd.DataFrame(rates)
    df["rsi"] = ta.momentum.RSIIndicator(df["close"], window=14).rsi()
    df["e9"]  = ta.trend.EMAIndicator(df["close"], window=9).ema_indicator()
    df["e21"] = ta.trend.EMAIndicator(df["close"], window=21).ema_indicator()
    macd_obj  = ta.trend.MACD(df["close"])
    df["mc"]  = macd_obj.macd()
    df["ms"]  = macd_obj.macd_signal()
    bb        = ta.volatility.BollingerBands(df["close"], window=20, window_dev=2)
    df["bbl"] = bb.bollinger_lband()
    df["bbh"] = bb.bollinger_hband()

    r = df.iloc[-1]
    buy = sell = 0

    if r["rsi"] < 40:   buy  += 1
    elif r["rsi"] > 60: sell += 1

    if r["e9"] > r["e21"]:   buy  += 1
    elif r["e9"] < r["e21"]: sell += 1

    if r["mc"] > r["ms"]:   buy  += 1
    elif r["mc"] < r["ms"]: sell += 1

    if r["close"] < r["bbl"]:   buy  += 1
    elif r["close"] > r["bbh"]: sell += 1

    if buy  >= MIN_INDICATORS: return "BUY"
    if sell >= MIN_INDICATORS: return "SELL"
    return None

# ── Plaseaza ordin ────────────────────────────────────────────────────────────
def place_order(direction):
    info   = mt5.symbol_info(symbol)
    tick   = mt5.symbol_info_tick(symbol)
    pip    = info.point
    digits = info.digits

    if direction == "BUY":
        entry = tick.ask
        sl    = round(entry - SL_PIPS * pip, digits)
        tp    = round(entry + TP_PIPS * pip, digits)
        otype = mt5.ORDER_TYPE_BUY
    else:
        entry = tick.bid
        sl    = round(entry + SL_PIPS * pip, digits)
        tp    = round(entry - TP_PIPS * pip, digits)
        otype = mt5.ORDER_TYPE_SELL

    fm = info.filling_mode
    if fm & mt5.ORDER_FILLING_IOC:
        filling = mt5.ORDER_FILLING_IOC
    elif fm & mt5.ORDER_FILLING_FOK:
        filling = mt5.ORDER_FILLING_FOK
    else:
        filling = mt5.ORDER_FILLING_RETURN

    req = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         otype,
        "price":        entry,
        "sl":           sl,
        "tp":           tp,
        "deviation":    20,
        "magic":        MAGIC,
        "comment":      "xauusd_bot",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    result = mt5.order_send(req)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return True, sl, tp
    return False, sl, tp

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
            ts     = datetime.now().strftime("%H:%M:%S")
            now    = time.time()

            if spread > MAX_SPREAD:
                print(f"[{ts}] Pret: {price:.2f} | Spread prea mare (skip)")
                time.sleep(2)
                continue

            if (now - last_trade) < COOLDOWN:
                time.sleep(2)
                continue

            if open_positions() >= MAX_POS:
                time.sleep(2)
                continue

            signal = get_signal()

            if signal in ("BUY", "SELL"):
                ok, sl, tp = place_order(signal)
                if ok:
                    print(f"[{ts}] Pret: {price:.2f} | Semnal: {signal} | ✅ EXECUTAT | SL: {sl:.2f} | TP: {tp:.2f}")
                    last_trade = time.time()
                else:
                    print(f"[{ts}] Pret: {price:.2f} | Semnal: {signal} | ❌ Eroare executie")
            else:
                print(f"[{ts}] Pret: {price:.2f} | Fara semnal")

            time.sleep(2)

    except KeyboardInterrupt:
        print("\nBot oprit.")
        mt5.shutdown()

if __name__ == "__main__":
    run()
