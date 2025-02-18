import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY"),
    "BINANCE_SECRET": os.getenv("BINANCE_SECRET"),
    "KUCOIN_API_KEY": os.getenv("KUCOIN_API_KEY"),
    "KUCOIN_SECRET": os.getenv("KUCOIN_SECRET"),
    "BITGET_API_KEY": os.getenv("BITGET_API_KEY"),
    "BITGET_SECRET": os.getenv("BITGET_SECRET"),
    "BITSTAMP_API_KEY": os.getenv("BITSTAMP_API_KEY"),
    "BITSTAMP_SECRET": os.getenv("BITSTAMP_SECRET"),
    
    "ALLOWED_QUOTES": ["USDT", "EUR", "BTC"],

    "MIN_QUOTE_VOLUME": 1000,   # minimalny wolumen (w jednostkach danej waluty) wymagany do uwzględnienia rynku

    "ARBITRAGE_THRESHOLD": 0.5,  # próg arbitrażu w %

    "ABSURD_THRESHOLD": 100,     # próg absurdalnego zysku w %

    "INVESTMENT_AMOUNT": 100,    # kwota inwestycji (domyślnie w USDT)
    
    "CONVERT_INVESTMENT": {
        "BTC": True,
        "ETH": True
    }
}
