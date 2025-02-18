import ccxt.async_support as ccxt
from config import CONFIG
import asyncio

class BinanceExchange:
    def __init__(self):
        self.exchange = ccxt.binance({
            'apiKey': CONFIG["BINANCE_API_KEY"],
            'secret': CONFIG["BINANCE_SECRET"],
            'enableRateLimit': True,
            'options': {
                'default type' : 'spot'
            }
            
        })
        self.fee_rate = 0.1

    async def load_markets(self):
        return await self.exchange.load_markets()

    async def fetch_ticker(self, symbol):
        try:
            ticker = await self.exchange.fetch_ticker(symbol)
            return ticker
        except asyncio.CancelledError:
            # Propagujemy anulowanie, aby główny kod mógł go obsłużyć
            raise
        except Exception as e:
            print(f"Error fetching ticker from Binance: {e}")
            return None

    async def fetch_order_book(self, symbol):
        try:
            order_book = await self.exchange.fetch_order_book(symbol)
            return order_book
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"Error fetching order book from Binance: {e}")
            return None

    async def close(self):
        await self.exchange.close()
