# exchanges/kucoin.py

import aiohttp
import logging
from .exchange import Exchange

class KucoinExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = "https://api.kucoin.com/api/v1/symbols"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Zakładamy, że dane znajdują się w data["data"] i każdy element ma klucz "symbol"
                pairs = [item['symbol'] for item in data.get("data", [])]
                return pairs
        except Exception as e:
            logging.error(f"Kucoin get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        # Przykładowy endpoint – dostosuj do dokumentacji Kucoin!
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={pair}"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Zakładamy, że cena jest pod kluczem "price" w data["data"]
                price = float(data.get("data", {}).get("price", 0))
                return price
        except Exception as e:
            logging.error(f"Kucoin get_price error for {pair}: {e}")
            return None
