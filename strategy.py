# backend/strategy.py
    if index < lookback:
        return False

    current = candles[index]
    previous_lows = [c["low"] for c in candles[index - lookback:index]]
    return current["low"] < min(previous_lows) and current["close"] > min(previous_lows)


def swept_recent_high(candles, index, lookback=10):
    if index < lookback:
        return False

    current = candles[index]
    previous_highs = [c["high"] for c in candles[index - lookback:index]]
    return current["high"] > max(previous_highs) and current["close"] < max(previous_highs)


def analyze_market(symbol, candles):
    if len(candles) < 20:
        return {
            "symbol": symbol,
            "action": "WAIT",
            "reason": "Not enough candle data yet"
        }

    index = len(candles) - 1
    current = candles[index]
    previous = candles[index - 1]

    bullish_fvg = detect_bullish_fvg(candles, index)
    bearish_fvg = detect_bearish_fvg(candles, index)

    bullish_setup = (
        swept_recent_low(candles, index) and
        is_bullish_displacement(current, previous) and
        bullish_fvg is not None
    )

    bearish_setup = (
        swept_recent_high(candles, index) and
        is_bearish_displacement(current, previous) and
        bearish_fvg is not None
    )

    if bullish_setup:
        entry = (bullish_fvg["low"] + bullish_fvg["high"]) / 2
        stop_loss = current["low"]
        risk = entry - stop_loss
        take_profit = entry + risk * 2

        return {
            "setup_id": str(uuid.uuid4()),
            "symbol": symbol,
            "action": "BUY",
            "confidence": 0.65,
            "setup": "Liquidity sweep + bullish displacement + bullish FVG",
            "entry": round(entry, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "risk_reward": "1:2"
        }

    if bearish_setup:
        entry = (bearish_fvg["low"] + bearish_fvg["high"]) / 2
        stop_loss = current["high"]
        risk = stop_loss - entry
        take_profit = entry - risk * 2

        return {
            "setup_id": str(uuid.uuid4()),
            "symbol": symbol,
            "action": "SELL",
            "confidence": 0.65,
            "setup": "Liquidity sweep + bearish displacement + bearish FVG",
            "entry": round(entry, 2),
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "risk_reward": "1:2"
        }

    return {
        "symbol": symbol,
        "action": "WAIT",
        "confidence": 0.0,
        "reason": "No high-probability setup found"
    }