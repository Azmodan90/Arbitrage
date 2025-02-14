import ccxt
from config import CONFIG

class BitgetExchange:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': CONFIG["BITGET_API_KEY"],
            'secret': CONFIG["BITGET_SECRET"],
            'enableRateLimit': True,
        })
        self.fee_rate = 0.1

    def fetch_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Bitget: {e}")
            return None
