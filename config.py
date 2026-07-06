# ==========================================
# Configuration — all secrets come from environment variables (.env file)
# NEVER hardcode API keys in code. Copy .env.example to .env and fill it.
# ==========================================

import os


def _load_dotenv(path=".env"):
    """Tiny .env loader (no external dependency)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)


_load_dotenv()


def _env(name, default=""):
    return os.environ.get(name, default).strip()


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return float(default)


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return int(default)


# --- Secrets (set these in .env) ---
COINDCX_API_KEY = _env("COINDCX_API_KEY")
COINDCX_API_SECRET = _env("COINDCX_API_SECRET")
TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")

# --- Mode ---
# False = paper trading + Telegram signals only (SAFE, default)
# True  = real market orders on CoinDCX (crypto only; forex is always signal/paper)
USE_REAL_ORDERS = _env("USE_REAL_ORDERS", "false").lower() in ("1", "true", "yes")

# --- Watchlists ---
CRYPTO_WATCHLIST = [
    s.strip().upper()
    for s in _env("CRYPTO_WATCHLIST", "BTCINR,ETHINR,SOLINR,XRPINR,BNBINR,DOGEINR").split(",")
    if s.strip()
]
FOREX_WATCHLIST = [
    s.strip().upper()
    for s in _env("FOREX_WATCHLIST", "EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD").split(",")
    if s.strip()
]

# --- Strategy timeframe ---
TIMEFRAME = _env("TIMEFRAME", "5m")          # entry timeframe
TREND_TIMEFRAME = _env("TREND_TIMEFRAME", "1h")  # higher-timeframe trend filter
CANDLE_LIMIT = 300                            # candles fetched per scan

# --- Risk management ---
START_BALANCE = _env_float("START_BALANCE", 2000)   # paper balance (INR)
RISK_PER_TRADE = _env_float("RISK_PER_TRADE", 0.01) # 1% of balance risked per trade
MAX_OPEN_TRADES = _env_int("MAX_OPEN_TRADES", 3)
MAX_TRADES_PER_DAY = _env_int("MAX_TRADES_PER_DAY", 15)
DAILY_MAX_LOSS_PCT = _env_float("DAILY_MAX_LOSS_PCT", 0.03)  # stop for the day at -3%
COOLDOWN_MIN = _env_int("COOLDOWN_MIN", 30)  # minutes before re-trading same symbol

# --- ATR-based dynamic SL/TP (the bot sets these itself per trade) ---
ATR_PERIOD = 14
SL_ATR_MULT = 1.5     # stop loss   = 1.5 x ATR below entry
TP_ATR_MULT = 3.0     # take profit = 3.0 x ATR above entry  (1:2 risk-reward)
TRAIL_ATR_MULT = 2.0  # chandelier trailing stop distance
BREAKEVEN_ATR = 1.0   # after +1 x ATR in profit, move SL to entry (risk-free)

# --- Indicator settings ---
EMA_FAST = 9
EMA_SLOW = 21
EMA_TREND = 200
RSI_PERIOD = 14
RSI_LONG_MIN, RSI_LONG_MAX = 45, 70    # longs: momentum but not overbought
RSI_SHORT_MIN, RSI_SHORT_MAX = 30, 55  # shorts: momentum but not oversold

# --- Loop ---
SCAN_DELAY = _env_int("SCAN_DELAY", 60)  # seconds between scans

# --- Files ---
JOURNAL_FILE = _env("JOURNAL_FILE", "trades.csv")
