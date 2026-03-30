import math
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

# ═══════════════════════════════════════════
# COMPOUNDING / PROFIT MANAGEMENT
# ═══════════════════════════════════════════
PROFIT_TARGET_PCT = 1.5        # Close all positions when profit reaches +1.5% of balance
MAX_LOSS_PCT      = 1.5        # Close all positions if loss reaches -1.5% of balance (safety)
REINVEST_PCT      = 50.0       # Reinvest 50% of profit into next cycle (lot size recalc)
BALANCE_USAGE_PCT   = 50.0     # Use 50% of effective balance for position sizing
MIN_LOT             = 0.01     # Minimum lot size allowed
MAX_LOT             = 100.0    # Maximum lot size allowed
DEFAULT_LEVERAGE    = 100      # Fallback leverage when MT5 cannot provide it
DEFAULT_VOLUME_STEP = 0.01     # Fallback volume step when broker info is unavailable

last_trade = 0
symbol     = None
lot        = 0.01

# ── Stare ciclu compounding ───────────────────────────────────────────────────
cycle_start_balance = None
cycle_number        = 0
effective_balance   = None
history             = []

# ── Conexiune MT5 ─────────────────────────────────────────────────────────────
def connect():
    global symbol, lot, cycle_start_balance, effective_balance
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

    cycle_start_balance = acc.balance
    effective_balance   = acc.balance

    recalculate_lot_size()
    print(f"Simbol: {symbol} | Lot calculat: {lot:.2f}\n")

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

# ── Recalculeaza lot pe baza a 50% din balanta efectiva ──────────────────────
def recalculate_lot_size():
    global lot, effective_balance
    if effective_balance is None:
        acc = mt5.account_info()
        if acc is None:
            return
        effective_balance = acc.balance

    sym_info = mt5.symbol_info(symbol)
    if sym_info is None:
        return

    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return

    # 50% of effective balance is the margin available for trading
    available_margin = effective_balance * (BALANCE_USAGE_PCT / 100.0)

    # Try to get exact margin for 1.0 lot from MT5
    margin_for_one_lot = mt5.order_calc_margin(
        mt5.ORDER_TYPE_BUY,
        symbol,
        1.0,
        tick.ask
    )

    if margin_for_one_lot is None or margin_for_one_lot <= 0:
        # Fallback: (price * contract_size) / leverage
        acc = mt5.account_info()
        leverage = acc.leverage if acc and acc.leverage > 0 else DEFAULT_LEVERAGE
        contract_size = sym_info.trade_contract_size  # usually 100 for XAUUSD
        margin_for_one_lot = (tick.ask * contract_size) / leverage

    if margin_for_one_lot > 0:
        new_lot = available_margin / margin_for_one_lot
    else:
        new_lot = MIN_LOT

    # Round down to broker volume step
    lot_step = sym_info.volume_step if sym_info.volume_step > 0 else DEFAULT_VOLUME_STEP
    new_lot  = math.floor(new_lot / lot_step) * lot_step

    # Clamp between broker min/max and our safety MAX_LOT
    vol_min = sym_info.volume_min if sym_info.volume_min > 0 else MIN_LOT
    vol_max = min(sym_info.volume_max, MAX_LOT) if sym_info.volume_max > 0 else MAX_LOT
    new_lot = max(vol_min, min(vol_max, new_lot))
    new_lot = round(new_lot, 2)

    old_lot = lot
    lot     = new_lot
    ts      = datetime.now().strftime("%H:%M:%S")
    msg = (f"[{ts}] Lot recalculat: {old_lot:.2f} → {new_lot:.2f} "
           f"({BALANCE_USAGE_PCT:.0f}% din ${effective_balance:.2f} = ${available_margin:.2f} marja | "
           f"marja/lot: ${margin_for_one_lot:.2f})")
    if len(history) >= 1000:
        del history[:500]
    history.append(msg)

# ── Inchide toate pozitiile deschise ──────────────────────────────────────────
def close_all_positions():
    positions = mt5.positions_get(symbol=symbol)
    if not positions:
        return
    for pos in positions:
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            continue
        if pos.type == mt5.ORDER_TYPE_BUY:
            price   = tick.bid
            otype   = mt5.ORDER_TYPE_SELL
        else:
            price   = tick.ask
            otype   = mt5.ORDER_TYPE_BUY

        info = mt5.symbol_info(symbol)
        fm   = info.filling_mode
        if fm & mt5.ORDER_FILLING_IOC:
            filling = mt5.ORDER_FILLING_IOC
        elif fm & mt5.ORDER_FILLING_FOK:
            filling = mt5.ORDER_FILLING_FOK
        else:
            filling = mt5.ORDER_FILLING_RETURN

        req = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       symbol,
            "volume":       pos.volume,
            "type":         otype,
            "position":     pos.ticket,
            "price":        price,
            "deviation":    20,
            "magic":        MAGIC,
            "comment":      "close_all",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": filling,
        }
        mt5.order_send(req)

# ── Verifica target profit / stop loss global ─────────────────────────────────
def check_profit_target():
    global cycle_start_balance, cycle_number, effective_balance
    if cycle_start_balance is None:
        return False

    acc = mt5.account_info()
    if acc is None:
        return False

    equity     = acc.equity
    current_pl = equity - cycle_start_balance
    pl_pct     = (current_pl / cycle_start_balance) * 100 if cycle_start_balance > 0 else 0.0
    ts         = datetime.now().strftime("%H:%M:%S")

    if pl_pct >= PROFIT_TARGET_PCT:
        close_all_positions()
        profit   = current_pl
        reinvest = profit * (REINVEST_PCT / 100.0)
        effective_balance = cycle_start_balance + reinvest
        cycle_number += 1
        new_acc = mt5.account_info()
        cycle_start_balance = new_acc.balance if new_acc else equity
        recalculate_lot_size()
        msg = (f"[{ts}] CICLU #{cycle_number} COMPLET! "
               f"Profit: +${profit:.2f} (+{pl_pct:.2f}%) | "
               f"Reinvestit: ${reinvest:.2f} | Nou lot: {lot:.2f}")
        if len(history) >= 1000:
            del history[:500]
        history.append(msg)
        print(msg)
        return True

    if pl_pct <= -MAX_LOSS_PCT:
        close_all_positions()
        msg = (f"[{ts}] STOP LOSS GLOBAL: {pl_pct:.2f}% | "
               f"Toate pozitiile inchise | Se continua cu lot recalculat")
        if len(history) >= 1000:
            del history[:500]
        history.append(msg)
        print(msg)
        new_acc = mt5.account_info()
        cycle_start_balance = new_acc.balance if new_acc else equity
        effective_balance   = cycle_start_balance
        recalculate_lot_size()
        return True

    return False

# ── Afiseaza status compounding ────────────────────────────────────────────────
def display_status(price):
    if cycle_start_balance is None:
        return
    acc = mt5.account_info()
    if acc is None:
        return
    equity     = acc.equity
    current_pl = equity - cycle_start_balance
    pl_pct     = (current_pl / cycle_start_balance) * 100 if cycle_start_balance > 0 else 0.0
    target_amt = cycle_start_balance * (PROFIT_TARGET_PCT / 100.0)
    sl_amt     = cycle_start_balance * (MAX_LOSS_PCT / 100.0)

    # Progress bar toward profit target (0–100%)
    progress = (max(0.0, min(1.0, pl_pct / PROFIT_TARGET_PCT))
                if pl_pct > 0 and PROFIT_TARGET_PCT > 0 else 0.0)
    bar_len  = 16
    filled   = int(bar_len * progress)
    bar      = "█" * filled + "░" * (bar_len - filled)
    pct_bar  = int(progress * 100)

    pl_sign = "+" if current_pl >= 0 else ""
    margin_used = effective_balance * (BALANCE_USAGE_PCT / 100.0)
    print(
        f"  ── COMPOUNDING STATUS ─────────────────────────\n"
        f"  Ciclu:              #{cycle_number}\n"
        f"  Balanta initiala:   ${cycle_start_balance:,.2f}\n"
        f"  Balanta efectiva:   ${effective_balance:,.2f}\n"
        f"  Marja utilizata:    {BALANCE_USAGE_PCT:.0f}% din balanta = ${margin_used:,.2f}\n"
        f"  Lot calculat:       {lot:.2f}\n"
        f"  Profit curent:      {pl_sign}${current_pl:.2f} ({pl_sign}{pl_pct:.2f}%)\n"
        f"  Target:             +{PROFIT_TARGET_PCT}% (${target_amt:,.2f})\n"
        f"  Stop Loss Global:   -{MAX_LOSS_PCT}% (${sl_amt:,.2f})\n"
        f"  Progress:           [{bar}] {pct_bar}%\n"
        f"  ───────────────────────────────────────────────"
    )

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
            # Check profit target / stop loss every tick
            check_profit_target()

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
                    print(f"[{ts}] Pret: {price:.2f} | Semnal: {signal} | ✅ EXECUTAT | SL: {sl:.2f} | TP: {tp:.2f} | Lot: {lot:.2f}")
                    last_trade = time.time()
                else:
                    print(f"[{ts}] Pret: {price:.2f} | Semnal: {signal} | ❌ Eroare executie")
            else:
                print(f"[{ts}] Pret: {price:.2f} | Fara semnal")

            display_status(price)
            time.sleep(2)

    except KeyboardInterrupt:
        print("\nBot oprit.")
        mt5.shutdown()

if __name__ == "__main__":
    run()
