#binance.py
import ccxt
from config import CONFIG

class BinanceExchange:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': CONFIG["BINANCE_API_KEY"],
            'secret': CONFIG["BINANCE_SECRET"],
            'enableRateLimit': True,
        })

    def fetch_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Binance: {e}")
            return None

    def create_order(self, symbol, order_type, side, amount, price=None):
        try:
            if order_type == 'market':
                return self.exchange.create_market_order(symbol, side, amount)
            elif order_type == 'limit':
                return self.exchange.create_limit_order(symbol, side, amount, price)
        except Exception as e:
            print(f"Error creating order on Binance: {e}")
            return None
