from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import json
import os
import uuid
from datetime import datetime

app = FastAPI(title="AI Trading Learning API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

####################################
# MEMORY
####################################

MEMORY_FILE = "ai_memory.json"

DEFAULT_MEMORY = {
    "total_trades": 0,
    "wins": 0,
    "losses": 0,
    "net_profit_loss": 0,
    "setups": {}
}


class AIBrain:
    def __init__(self):
        self.memory = self.load()

    def load(self):
        if not os.path.exists(MEMORY_FILE):
            return DEFAULT_MEMORY.copy()
        with open(MEMORY_FILE, "r") as f:
            return json.load(f)

    def save(self):
        with open(MEMORY_FILE, "w") as f:
            json.dump(self.memory, f, indent=4)

    def setup(self, name):
        if name not in self.memory["setups"]:
            self.memory["setups"][name] = {
                "trades": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "bonus": 0
            }
        return self.memory["setups"][name]

    def approve(self, signal):
        if signal["action"] == "WAIT":
            return {
                "approved": False,
                "reason": "No trade"
            }

        setup = self.setup(signal["setup"])
        confidence = signal["confidence"] + setup["bonus"]

        if setup["trades"] < 20:
            return {
                "approved": True,
                "mode": "LEARNING",
                "confidence": confidence
            }

        winrate = 0
        if setup["trades"]:
            winrate = setup["wins"] / setup["trades"]

        if confidence >= 0.65 and winrate >= 0.55:
            return {
                "approved": True,
                "mode": "PROVEN"
            }

        return {
            "approved": False,
            "reason": "Stats weak"
        }

    def learn(self, setup, won, pnl):
        s = self.setup(setup)

        self.memory["total_trades"] += 1
        self.memory["net_profit_loss"] += pnl

        s["trades"] += 1
        s["profit"] += pnl

        if won:
            s["wins"] += 1
            self.memory["wins"] += 1
            s["bonus"] = min(.15, s["bonus"] + .02)
        else:
            s["losses"] += 1
            self.memory["losses"] += 1
            s["bonus"] = max(-.25, s["bonus"] - .03)

        self.save()

        return {
            "status": "learned",
            "memory": self.memory
        }


brain = AIBrain()

####################################
# PAPER BROKER
####################################


class PaperBroker:
    def __init__(self):
        self.balance = 50000
        self.trades = []

    def place_trade(self, symbol, side, entry, sl, tp, risk=.5):
        dollars = self.balance * (risk / 100)

        trade = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "stop": sl,
            "target": tp,
            "risk_dollars": round(dollars, 2),
            "time": datetime.utcnow().isoformat()
        }

        self.trades.append(trade)
        return trade


paper = PaperBroker()

####################################
# BROKERS
####################################

BROKERS = {
    "topstep": {
        "name": "Topstep",
        "website": "https://www.topstep.com",
        "note": "Topstep connects through platforms like Tradovate or NinjaTrader.",
        "connect_type": "platform_redirect",
        "paper": True
    },
    "lucid": {
        "name": "Lucid Trading",
        "website": "https://lucidtrading.com",
        "note": "Use only if they provide an official API connection.",
        "connect_type": "manual_api",
        "paper": True
    },
    "tradovate_demo": {
        "name": "Tradovate Demo",
        "website": "https://demo.tradovateapi.com",
        "note": "Good for futures demo/paper trading.",
        "connect_type": "api_key",
        "paper": True
    },
    "alpaca_paper": {
        "name": "Alpaca Paper",
        "website": "https://app.alpaca.markets/paper/dashboard/overview",
        "note": "Good for stock/crypto paper trading.",
        "connect_type": "api_key",
        "paper": True
    },
    "future_live": {
        "name": "Live Trading",
        "website": "#",
        "note": "Live trading - use with caution.",
        "connect_type": "api_key",
        "paper": False
    }
}

CONNECTED_BROKERS = {}

####################################
# STRATEGY
####################################


def bullish_displacement(current, previous):
    current_body = abs(current["close"] - current["open"])
    previous_body = abs(previous["close"] - previous["open"])
    return (
        current["close"] > current["open"]
        and current_body > previous_body * 1.8
    )


def bearish_displacement(current, previous):
    current_body = abs(current["close"] - current["open"])
    previous_body = abs(previous["close"] - previous["open"])
    return (
        current["close"] < current["open"]
        and current_body > previous_body * 1.8
    )


def liquidity_low(candles, idx):
    lows = [x["low"] for x in candles[-10:]]
    return candles[idx]["low"] < min(lows)


def liquidity_high(candles, idx):
    highs = [x["high"] for x in candles[-10:]]
    return candles[idx]["high"] > max(highs)


def strategy(symbol, candles):
    if len(candles) < 20:
        return {"action": "WAIT"}

    current = candles[-1]
    previous = candles[-2]

    if liquidity_low(candles, -1) and bullish_displacement(current, previous):
        return {
            "setup": "Liquidity+BullishDisplacement",
            "setup_id": str(uuid.uuid4()),
            "symbol": symbol,
            "action": "BUY",
            "entry": current["close"],
            "stop_loss": current["low"],
            "take_profit": current["close"] + (current["close"] - current["low"]) * 2,
            "confidence": .65
        }

    if liquidity_high(candles, -1) and bearish_displacement(current, previous):
        return {
            "setup": "Liquidity+BearishDisplacement",
            "setup_id": str(uuid.uuid4()),
            "symbol": symbol,
            "action": "SELL",
            "entry": current["close"],
            "stop_loss": current["high"],
            "take_profit": current["close"] - (current["high"] - current["close"]) * 2,
            "confidence": .65
        }

    return {"action": "WAIT"}


####################################
# MODELS
####################################


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float


class Market(BaseModel):
    symbol: str
    broker: str = "tradovate_demo"
    candles: list[Candle]


class Learn(BaseModel):
    setup: str
    won: bool
    pnl: float


class BrokerKeys(BaseModel):
    broker_id: str
    api_key: str
    api_secret: str
    account_id: str | None = None
    paper: bool = True


####################################
# API
####################################


@app.get("/")
def home():
    return {"status": "running"}


@app.get("/brokers")
def brokers():
    return BROKERS


@app.get("/connect/{broker_id}")
def connect_broker_link(broker_id: str):
    if broker_id not in BROKERS:
        raise HTTPException(status_code=404, detail="Broker not found")
    broker = BROKERS[broker_id]
    return RedirectResponse(url=broker["website"])


@app.post("/attach-broker")
def attach_broker(keys: BrokerKeys):
    if keys.broker_id not in BROKERS:
        raise HTTPException(status_code=404, detail="Broker not found")

    connection_id = str(uuid.uuid4())

    CONNECTED_BROKERS[connection_id] = {
        "broker_id": keys.broker_id,
        "broker_name": BROKERS[keys.broker_id]["name"],
        "api_key": keys.api_key,
        "api_secret": keys.api_secret,
        "account_id": keys.account_id,
        "paper": keys.paper,
        "status": "connected"
    }

    return {
        "status": "broker_attached",
        "connection_id": connection_id,
        "broker": BROKERS[keys.broker_id]["name"],
        "paper_mode": keys.paper
    }


@app.get("/connected-brokers")
def connected_brokers():
    safe = []
    for connection_id, broker in CONNECTED_BROKERS.items():
        safe.append({
            "connection_id": connection_id,
            "broker_id": broker["broker_id"],
            "broker_name": broker["broker_name"],
            "account_id": broker["account_id"],
            "paper": broker["paper"],
            "status": broker["status"]
        })
    return safe


@app.get("/memory")
def memory():
    return brain.memory


@app.post("/analyze")
def analyze(market: Market):
    candles = [x.dict() for x in market.candles]
    signal = strategy(market.symbol, candles)
    decision = brain.approve(signal)
    return {
        "signal": signal,
        "decision": decision
    }


@app.post("/auto-trade")
def trade(market: Market):
    candles = [x.dict() for x in market.candles]
    signal = strategy(market.symbol, candles)
    decision = brain.approve(signal)

    if not decision["approved"]:
        return {"status": "NO"}

    broker = BROKERS[market.broker]

    if not broker["paper"]:
        return {
            "status": "BLOCKED",
            "reason": "Live disabled"
        }

    trade = paper.place_trade(
        market.symbol,
        signal["action"],
        signal["entry"],
        signal["stop_loss"],
        signal["take_profit"]
    )

    return {
        "status": "PLACED",
        "trade": trade
    }


@app.post("/learn")
def learn(result: Learn):
    return brain.learn(result.setup, result.won, result.pnl)
