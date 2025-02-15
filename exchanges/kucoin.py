import ccxt
import asyncio
from config import CONFIG

class KucoinExchange:
    def __init__(self):
        self.exchange = ccxt.kucoin({
            'apiKey': CONFIG["KUCOIN_API_KEY"],
            'secret': CONFIG["KUCOIN_SECRET"],
            'enableRateLimit': True,
        })
        self.fee_rate = 0.1
        self.semaphore = asyncio.Semaphore(5)

    async def fetch_ticker_limited(self, symbol):
        async with self.semaphore:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self.exchange.fetch_ticker, symbol)

    def fetch_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Kucoin: {e}")
            return None
