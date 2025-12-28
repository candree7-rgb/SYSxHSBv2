import re
import hashlib
from typing import Any, Dict, Optional, List

NUM = r"([0-9]+(?:\.[0-9]+)?)"

# ============================================================
# AO TRADING FORMAT
# ============================================================
# Beispiel-Signal:
# 🔴 SHORT SIGNAL - AT/USDT
# Leverage: 25x • Trader: haseeb1111
# 📊 Entry: 0.16200 ✅ Triggered
# 🎯 Profit Targets:
# ✅ TP1: 0.16006 HIT (+30.00%)
# 🎯 TP4: 0.14904 → NEXT
# 📊 DCA Levels:
# ⏳ DCA1: 0.16590 Pending
# 🛡️ Stop Loss: 0.16200
# ============================================================

# Symbol and Side: "🔴 SHORT SIGNAL - AT/USDT" oder "🟢 LONG SIGNAL - AT/USDT"
# Auch ohne Emoji: "SHORT SIGNAL - AT/USDT"
RE_SYMBOL_SIDE = re.compile(
    r"(LONG|SHORT)\s+SIGNAL\s*[-–—]\s*([A-Z0-9]+)/([A-Z]+)",
    re.I
)

# Entry: "📊 Entry: 0.16200" (optional mit Status wie ✅ Triggered, ⏳ Pending)
RE_ENTRY = re.compile(
    r"Entry\s*:\s*\$?" + NUM,
    re.I
)

# TP: verschiedene Formate:
# "✅ TP1: 0.16006 HIT (+30.00%)"
# "🎯 TP4: 0.14904 → NEXT"
# "⏳ TP2: 0.15811 Pending"
RE_TP = re.compile(
    r"TP(\d+)\s*:\s*\$?" + NUM,
    re.I
)

# DCA: "⏳ DCA1: 0.16590 Pending" (nur 1 DCA oder keines)
RE_DCA = re.compile(
    r"DCA(\d+)\s*:\s*\$?" + NUM,
    re.I
)

# Stop Loss: "🛡️ Stop Loss: 0.16200" (optional mit Status wie ❌ HIT, ✅ Moved to Breakeven)
RE_SL = re.compile(
    r"Stop\s*Loss\s*:\s*\$?" + NUM,
    re.I
)

# Leverage: "Leverage: 25x"
RE_LEVERAGE = re.compile(
    r"Leverage\s*:\s*(\d+)x",
    re.I
)

# Trader/Caller: "Trader: haseeb1111" oder "Caller: haseeb1111"
RE_TRADER = re.compile(
    r"(?:Trader|Caller)\s*:\s*(\w+)",
    re.I
)

# Status patterns to detect if trade is still valid for entry
RE_AWAITING = re.compile(r"AWAITING\s+ENTRY|Pending", re.I)
RE_CLOSED = re.compile(r"TRADE\s+CLOSED|CLOSED\s+AT\s+BREAKEVEN|TRADE\s+CANCELLED", re.I)


def parse_signal(text: str, quote: str = "USDT") -> Optional[Dict[str, Any]]:
    """
    Parse AO Trading signal format.

    Returns None if:
    - Not a NEW SIGNAL message
    - Trade is already CLOSED/CANCELLED
    - Cannot parse symbol/side or entry price
    """
    # We only want fresh "NEW SIGNAL" entries, not closed summaries
    if "NEW SIGNAL" not in text.upper():
        return None

    # Skip already closed/cancelled trades
    if RE_CLOSED.search(text):
        return None

    # Parse symbol and side
    ms = RE_SYMBOL_SIDE.search(text)
    if not ms:
        return None

    side_word = ms.group(1).upper()
    base = ms.group(2).upper()
    quote_from_signal = ms.group(3).upper()

    side = "sell" if side_word == "SHORT" else "buy"
    symbol = f"{base}{quote_from_signal}"

    # Parse entry/trigger price
    mtr = RE_ENTRY.search(text)
    if not mtr:
        return None
    trigger = float(mtr.group(1))

    # Parse TP prices
    tps: List[float] = []
    for m in RE_TP.finditer(text):
        idx = int(m.group(1))
        price = float(m.group(2))
        # Keep in order
        while len(tps) < idx:
            tps.append(0.0)
        tps[idx-1] = price
    tps = [p for p in tps if p > 0]

    # Parse DCA prices (only 1 or none in AO Trading)
    dcas: List[float] = []
    for m in RE_DCA.finditer(text):
        idx = int(m.group(1))
        price = float(m.group(2))
        while len(dcas) < idx:
            dcas.append(0.0)
        dcas[idx-1] = price
    dcas = [p for p in dcas if p > 0]

    # Parse Stop Loss
    sl = None
    msl = RE_SL.search(text)
    if msl:
        sl = float(msl.group(1))

    # Parse leverage (optional, for logging)
    leverage = None
    mlev = RE_LEVERAGE.search(text)
    if mlev:
        leverage = int(mlev.group(1))

    # Parse trader (optional, for logging)
    trader = None
    mtr2 = RE_TRADER.search(text)
    if mtr2:
        trader = mtr2.group(1)

    return {
        "base": base,
        "symbol": symbol,
        "side": side,          # buy / sell
        "trigger": trigger,
        "tp_prices": tps,
        "dca_prices": dcas,
        "sl_price": sl,
        "leverage": leverage,  # Optional: leverage from signal
        "trader": trader,      # Optional: trader name
        "raw": text,
    }


def signal_hash(sig: Dict[str, Any]) -> str:
    """Generate unique hash for signal deduplication."""
    core = f"{sig.get('symbol')}|{sig.get('side')}|{sig.get('trigger')}|{sig.get('tp_prices')}|{sig.get('dca_prices')}"
    return hashlib.md5(core.encode("utf-8")).hexdigest()
