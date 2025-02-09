#bitstamp.py
import ccxt
from config import CONFIG

class BitstampExchange:
    def __init__(self):
        self.exchange = ccxt.bitstamp({
            'apiKey': CONFIG["BITSTAMP_API_KEY"],
            'secret': CONFIG["BITSTAMP_SECRET"],
            'enableRateLimit': True,
        })

    def fetch_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Bitstamp: {e}")
            return None

    # Metoda tworzenia zleceń nie jest obecnie wykorzystywana.
    # def create_order(self, symbol, order_type, side, amount, price=None):
    #     pass
