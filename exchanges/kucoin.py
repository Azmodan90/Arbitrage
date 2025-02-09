import ccxt
from config import CONFIG

class KucoinExchange:
    def __init__(self):
        self.exchange = ccxt.kucoin({
            'apiKey': CONFIG["KUCOIN_API_KEY"],
            'secret': CONFIG["KUCOIN_SECRET"],
            'enableRateLimit': True,
        })
        self.fee_rate = 0.1

    def fetch_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Kucoin: {e}")
            return None
