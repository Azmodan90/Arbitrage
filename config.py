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
    
    # Lista dozwolonych quote – teraz możesz dodać dowolne, np. USDT, EUR, BTC, ETH itd.
    "ALLOWED_QUOTES": ["USDT", "EUR", "BTC", "ETH"],
    
    "ARBITRAGE_THRESHOLD": 0.5,  # próg arbitrażu (w %)
    "ABSURD_THRESHOLD": 100,     # próg absurdalnego zysku (w %)
    
    # Inwestycja podana w USDT
    "INVESTMENT_AMOUNT": 1000,
    
    # Dla których quote należy dokonać konwersji z USDT (np. BTC lub ETH)
    "CONVERT_INVESTMENT": {
         "USDT": False,
         "EUR": False,
         "BTC": True,
         "ETH": True
    }
}
