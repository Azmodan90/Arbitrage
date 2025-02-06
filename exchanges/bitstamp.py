# exchanges/bitstamp.py

import aiohttp
import logging
from .exchange import Exchange

class BitstampExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        # Endpoint Bitstamp zwracający informacje o dostępnych parach
        url = "https://www.bitstamp.net/api/v2/trading-pairs-info/"
        try:
            async with session.get(url) as response:
                data = await response.json()
                pairs = []
                # Dane to lista obiektów; zakładamy, że każdy obiekt ma pole "url_symbol"
                for product in data:
                    url_symbol = product.get("url_symbol")
                    if url_symbol:
                        # Możemy chcieć konwertować na uppercase np. "BTCUSD"
                        pairs.append(url_symbol.upper())
                return pairs
        except Exception as e:
            logging.error(f"Bitstamp get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        # Bitstamp oczekuje, że para będzie zapisana w formacie lowercase, np. "btcusd"
        pair_lower = pair.lower()
        url = f"https://www.bitstamp.net/api/v2/ticker/{pair_lower}/"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Ostatnia cena zwykle jest pod kluczem "last"
                price = float(data.get("last", 0))
                return price
        except Exception as e:
            logging.error(f"Bitstamp get_price error for {pair}: {e}")
            return None
