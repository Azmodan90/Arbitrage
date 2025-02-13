# binance.py - asynchroniczna wersja
import ccxt.async_support as ccxt
from config import CONFIG

class BinanceExchange:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': CONFIG["BINANCE_API_KEY"],
            'secret': CONFIG["BINANCE_SECRET"],
            'enableRateLimit': True,
        })
        self.fee_rate = 0.1

    async def fetch_ticker(self, symbol):
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Binance: {e}")
            return None

    async def fetch_order_book(self, symbol):
        try:
            order_book = await self.exchange.fetch_order_book(symbol)
            return order_book
        except Exception as e:
            print(f"Error fetching order book from Binance: {e}")
            return None
