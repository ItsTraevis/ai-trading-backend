from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import json
import os
import uuid
import requests
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
    "paper_local": {
        "name": "Paper Local",
        "website": "#",
        "note": "Local paper trading - no real money involved.",
        "connect_type": "local",
        "paper": True
    },
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
        "connect_type": "tradovate",
        "auth_url": "https://demo.tradovateapi.com/v1/auth/accesstokenrequest",
        "order_url": "https://demo.tradovateapi.com/v1/order/placeorder",
        "paper": True
    },
    "tradovate_live": {
        "name": "Tradovate Live",
        "website": "https://live.tradovateapi.com",
        "note": "Live futures trading - use with caution!",
        "connect_type": "tradovate",
        "auth_url": "https://live.tradovateapi.com/v1/auth/accesstokenrequest",
        "order_url": "https://live.tradovateapi.com/v1/order/placeorder",
        "paper": False
    },
    "alpaca_paper": {
        "name": "Alpaca Paper",
        "website": "https://app.alpaca.markets/paper/dashboard/overview",
        "note": "Good for stock/crypto paper trading.",
        "connect_type": "api_key",
        "paper": True
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


class TradovateLogin(BaseModel):
    username: str
    password: str
    app_id: str = "AITrader"
    app_version: str = "1.0"
    cid: int
    secret: str
    demo: bool = True


class PlaceTradeOrder(BaseModel):
    connection_id: str
    account_id: int
    symbol: str
    side: str
    quantity: int
    live_confirm: bool = False


class LearnTradeResult(BaseModel):
    trade_id: str
    won: bool
    profit_loss: float


class BacktestRequest(BaseModel):
    symbol: str
    candles: list[Candle]


# Trade history storage
TRADES_FILE = "trades.json"
trade_history = []

def load_trades():
    global trade_history
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, "r") as f:
            trade_history = json.load(f)

def save_trades():
    with open(TRADES_FILE, "w") as f:
        json.dump(trade_history, f, indent=4)

load_trades()


####################################
# API
####################################


@app.get("/")
def home():
    return {"status": "running"}


@app.get("/dashboard")
def dashboard():
    return {
        "brain": brain.memory,
        "paper_balance": paper.balance,
        "open_trades": len(paper.trades),
        "trade_history_count": len(trade_history),
        "connected_brokers": len(CONNECTED_BROKERS),
        "available_brokers": list(BROKERS.keys())
    }


@app.get("/brokers")
def brokers():
    return BROKERS


@app.get("/connections")
def connections():
    safe = []
    for connection_id, broker in CONNECTED_BROKERS.items():
        safe.append({
            "connection_id": connection_id,
            "broker_id": broker["broker_id"],
            "broker_name": broker["broker_name"],
            "account_id": broker.get("account_id"),
            "paper": broker["paper"],
            "status": broker["status"]
        })
    return safe


@app.get("/connect/{broker_id}")
def connect_broker_link(broker_id: str):
    if broker_id not in BROKERS:
        raise HTTPException(status_code=404, detail="Broker not found")
    broker = BROKERS[broker_id]
    return RedirectResponse(url=broker["website"])


@app.post("/attach-manual-broker")
def attach_manual_broker(keys: BrokerKeys):
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


@app.post("/connect-tradovate")
def connect_tradovate(login: TradovateLogin):
    broker_id = "tradovate_demo" if login.demo else "tradovate_live"
    broker = BROKERS[broker_id]

    payload = {
        "name": login.username,
        "password": login.password,
        "appId": login.app_id,
        "appVersion": login.app_version,
        "cid": login.cid,
        "sec": login.secret
    }

    try:
        response = requests.post(broker["auth_url"], json=payload, timeout=10)
        data = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection failed: {str(e)}")

    if "accessToken" not in data:
        raise HTTPException(status_code=401, detail=data)

    connection_id = str(uuid.uuid4())

    CONNECTED_BROKERS[connection_id] = {
        "broker_id": broker_id,
        "broker_name": broker["name"],
        "access_token": data["accessToken"],
        "paper": login.demo,
        "status": "connected"
    }

    return {
        "status": "connected",
        "connection_id": connection_id,
        "broker": broker["name"],
        "demo": login.demo
    }


@app.post("/place-trade")
def place_trade_order(order: PlaceTradeOrder):
    if order.connection_id not in CONNECTED_BROKERS:
        raise HTTPException(status_code=404, detail="Broker not connected")

    connection = CONNECTED_BROKERS[order.connection_id]
    broker = BROKERS[connection["broker_id"]]

    # Safety check for live trading
    if connection["paper"] is False and order.live_confirm is not True:
        return {
            "status": "blocked",
            "reason": "Live trading blocked. Set live_confirm=true only when ready."
        }

    action = order.side.upper()
    if action not in ["BUY", "SELL"]:
        raise HTTPException(status_code=400, detail="side must be BUY or SELL")

    tradovate_action = "Buy" if action == "BUY" else "Sell"

    payload = {
        "accountSpec": str(order.account_id),
        "accountId": order.account_id,
        "action": tradovate_action,
        "symbol": order.symbol,
        "orderQty": order.quantity,
        "orderType": "Market",
        "isAutomated": True
    }

    headers = {
        "Authorization": f"Bearer {connection['access_token']}"
    }

    try:
        response = requests.post(
            broker["order_url"],
            json=payload,
            headers=headers,
            timeout=10
        )
        result = response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Order failed: {str(e)}")

    return {
        "status": "order_sent",
        "broker": connection["broker_name"],
        "response": result
    }


@app.get("/memory")
def memory():
    return brain.memory


@app.post("/analyze-market")
def analyze_market(market: Market):
    candles = [x.dict() for x in market.candles]
    signal = strategy(market.symbol, candles)
    decision = brain.approve(signal)
    return {
        "signal": signal,
        "decision": decision
    }


@app.post("/ai-trade")
def ai_trade(market: Market):
    candles = [x.dict() for x in market.candles]
    signal = strategy(market.symbol, candles)
    decision = brain.approve(signal)

    if not decision["approved"]:
        return {"status": "NO_TRADE", "signal": signal, "decision": decision}

    broker = BROKERS[market.broker]

    if not broker["paper"]:
        return {
            "status": "BLOCKED",
            "reason": "Live disabled"
        }

    paper_trade = paper.place_trade(
        market.symbol,
        signal["action"],
        signal["entry"],
        signal["stop_loss"],
        signal["take_profit"]
    )

    # Save to trade history
    trade_record = {
        "trade_id": paper_trade["id"],
        "created_at": paper_trade["time"],
        "symbol": market.symbol,
        "broker": market.broker,
        "setup": signal.get("setup"),
        "side": signal["action"],
        "entry": signal["entry"],
        "stop_loss": signal["stop_loss"],
        "take_profit": signal["take_profit"],
        "confidence": signal.get("confidence"),
        "decision": decision,
        "learned": False,
        "won": None,
        "profit_loss": None,
    }
    trade_history.append(trade_record)
    save_trades()

    return {
        "status": "PLACED",
        "trade": paper_trade,
        "signal": signal,
        "decision": decision
    }


@app.post("/learn")
def learn(result: Learn):
    return brain.learn(result.setup, result.won, result.pnl)


@app.get("/trades")
def get_trades():
    return trade_history


@app.post("/learn-trade")
def learn_trade(result: LearnTradeResult):
    global trade_history
    
    for trade in trade_history:
        if trade["trade_id"] == result.trade_id:
            if trade.get("learned"):
                return {"status": "already_learned", "trade_id": result.trade_id}
            
            trade["won"] = result.won
            trade["profit_loss"] = result.profit_loss
            trade["learned"] = True
            
            # Update AI brain
            if trade.get("setup"):
                brain.learn(trade["setup"], result.won, result.profit_loss)
            
            save_trades()
            return {"status": "learned", "trade": trade}
    
    raise HTTPException(status_code=404, detail="Trade not found")


@app.post("/backtest")
def backtest(req: BacktestRequest):
    candles = [c.dict() for c in req.candles]
    if len(candles) < 50:
        raise HTTPException(status_code=400, detail="Need at least 50 candles for backtest")
    
    results = {
        "total_signals": 0,
        "buys": 0,
        "sells": 0,
        "waits": 0,
        "signals": []
    }
    
    for i in range(20, len(candles)):
        signal = strategy(req.symbol, candles[:i+1])
        if signal["action"] != "WAIT":
            results["total_signals"] += 1
            results["signals"].append({
                "index": i,
                "time": candles[i]["time"],
                **signal
            })
            if signal["action"] == "BUY":
                results["buys"] += 1
            else:
                results["sells"] += 1
        else:
            results["waits"] += 1
    
    return results


@app.post("/reset-paper-data")
def reset_paper_data():
    global trade_history
    
    brain.memory = DEFAULT_MEMORY.copy()
    brain.save()
    
    trade_history = []
    save_trades()
    
    paper.balance = 50000
    paper.trades = []
    
    return {"status": "reset_complete"}
