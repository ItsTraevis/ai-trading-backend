# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from strategy import analyze_market
from learning_engine import update_learning_score
from paper_broker import PaperBroker

app = FastAPI(title="AI Trading Learning API")

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

paper_broker = PaperBroker(starting_balance=50000)

class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0

class MarketRequest(BaseModel):
    symbol: str
    candles: list[Candle]

class TradeFeedback(BaseModel):
    setup_id: str
    won: bool
    profit_loss: float

@app.get("/")
def home():
    return {"status": "AI Trading API is running"}

@app.post("/analyze")
def analyze(request: MarketRequest):
    candles = [c.dict() for c in request.candles]
    signal = analyze_market(request.symbol, candles)
    return signal

@app.post("/paper-trade")
def paper_trade(request: MarketRequest):
    candles = [c.dict() for c in request.candles]
    signal = analyze_market(request.symbol, candles)

    if signal["action"] in ["BUY", "SELL"]:
        trade = paper_broker.place_trade(
            symbol=request.symbol,
            side=signal["action"],
            entry=signal["entry"],
            stop_loss=signal["stop_loss"],
            take_profit=signal["take_profit"],
            risk_percent=1
        )
        return {"signal": signal, "paper_trade": trade}

    return {"signal": signal, "paper_trade": None}

@app.post("/learn")
def learn(feedback: TradeFeedback):
    result = update_learning_score(
        setup_id=feedback.setup_id,
        won=feedback.won,
        profit_loss=feedback.profit_loss
    )
    return result
