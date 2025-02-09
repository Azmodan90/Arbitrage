import ccxt
from config import CONFIG

class BinanceExchange:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': CONFIG["BINANCE_API_KEY"],
            'secret': CONFIG["BINANCE_SECRET"],
            'enableRateLimit': True,
        })
        # Ustawiamy fee_rate – przykładowo 0.1%
        self.fee_rate = 0.1

    def fetch_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Binance: {e}")
