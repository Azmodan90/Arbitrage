import ccxt.async_support as ccxt
from config import CONFIG

class BitstampExchange:
    def __init__(self):
        self.exchange = ccxt.bitstamp({
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
