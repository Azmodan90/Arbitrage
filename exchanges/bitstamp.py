import ccxt.async_support as ccxt_async
from config import CONFIG

class BitstampExchange:
    def __init__(self):
        self.exchange = ccxt_async.bitstamp({
            'apiKey': CONFIG["BITSTAMP_API_KEY"],
            'secret': CONFIG["BITSTAMP_SECRET"],
            'enableRateLimit': True,
        })
        self.fee_rate = 0.25

    async def fetch_ticker(self, symbol):
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Bitstamp: {e}")
            return None

    async def load_markets(self):
        try:
            return await self.exchange.load_markets()
        except Exception as e:
            print(f"Error loading markets from Bitstamp: {e}")
            return {}

    async def fetch_order_book(self, symbol, limit=5):
        try:
            order_book = await self.exchange.fetch_order_book(symbol, params={'limit': limit})
            return order_book
        except Exception as e:
            print(f"Error fetching order book from Bitstamp: {e}")
            return None

    async def close(self):
        await self.exchange.close()
