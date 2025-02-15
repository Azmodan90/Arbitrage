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
    
    "ARBITRAGE_THRESHOLD": 0.5,  # minimalny zysk procentowy, aby sprawdzać order book
    "ABSURD_THRESHOLD": 100,     # powyżej tej wartości okazje są traktowane jako absurdalne
    "INVESTMENT_AMOUNT": 100      # kwota inwestycji w USDT
}
