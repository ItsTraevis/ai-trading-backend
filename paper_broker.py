# backend/paper_broker.py
class PaperBroker:
    def __init__(self, starting_balance=50000):
        self.balance = starting_balance
        self.trades = []

    def place_trade(self, symbol, side, entry, stop_loss, take_profit, risk_percent=1):
        risk_amount = self.balance * (risk_percent / 100)
        risk_per_unit = abs(entry - stop_loss)

        if risk_per_unit == 0:
            return {"error": "Invalid stop loss"}

        position_size = risk_amount / risk_per_unit

        trade = {
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "risk_amount": round(risk_amount, 2),
            "position_size": round(position_size, 2),
            "status": "OPEN"
        }

        self.trades.append(trade)
        return trade