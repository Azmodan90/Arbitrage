import ccxt
from config import CONFIG

class BinanceExchange:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': CONFIG["BINANCE_API_KEY"],
            'secret': CONFIG["BINANCE_SECRET"],
            'enableRateLimit': True,
        })
        self.fee_rate = 0.1

    def fetch_ticker(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker
        except Exception as e:
            print(f"Error fetching ticker from Binance: {e}")

    def close(self):
        # Dla instancji synchronicznych giełd ccxt nie ma metody close,
        # więc najpierw sprawdzamy, czy taka metoda istnieje.
        if hasattr(self.exchange, 'close'):
            self.exchange.close()
