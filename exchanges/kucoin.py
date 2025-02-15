import ccxt.async_support as ccxt_async
from config import CONFIG
import asyncio

class KucoinExchange:
    def __init__(self):
        self.exchange = ccxt_async.kucoin({
            'apiKey': CONFIG["KUCOIN_API_KEY"],
            'secret': CONFIG["KUCOIN_SECRET"],
            'enableRateLimit': True,
        })
        self.fee_rate = 0.1
        self.semaphore = asyncio.Semaphore(5)

    async def fetch_ticker(self, symbol):
        async with self.semaphore:
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                return ticker
            except Exception as e:
                print(f"Error fetching ticker from Kucoin: {e}")
                return None

    async def load_markets(self):
        try:
            return await self.exchange.load_markets()
        except Exception as e:
            print(f"Error loading markets from Kucoin: {e}")
            return {}

    async def fetch_order_book(self, symbol, limit=5):
        try:
            order_book = await self.exchange.fetch_order_book(symbol, params={'limit': limit})
            return order_book
        except Exception as e:
            print(f"Error fetching order book from Kucoin: {e}")
            return None

    async def close(self):
        await self.exchange.close()
