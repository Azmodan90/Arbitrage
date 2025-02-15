import ccxt.async_support as ccxt
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

    async def fetch_ticker(self, symbol):
        async with self.semaphore:
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                return ticker
            except Exception as e:
                print(f"Error fetching ticker from Kucoin: {e}")
                return None
