# exchanges/binance.py

import aiohttp
import logging
from .exchange import Exchange

class BinanceExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = "https://api.binance.com/api/v3/exchangeInfo"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Pobieramy listę symboli, np. "BTCUSDT", "ETHUSDT", itp.
                pairs = [symbol['symbol'] for symbol in data.get("symbols", [])]
                return pairs
        except Exception as e:
            logging.error(f"Binance get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={pair}"
        try:
            async with session.get(url) as response:
                data = await response.json()
                price = float(data.get("price", 0))
                return price
        except Exception as e:
            logging.error(f"Binance get_price error for {pair}: {e}")
            return None
