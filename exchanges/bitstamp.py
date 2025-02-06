import aiohttp
import logging
from .exchange import Exchange

class BitstampExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = "https://www.bitstamp.net/api/v2/trading-pairs-info/"
        try:
            async with session.get(url) as response:
                data = await response.json()
                pairs = []
                for product in data:
                    url_symbol = product.get("url_symbol")
                    if url_symbol:
                        pairs.append(url_symbol.upper())
                logging.info(f"Bitstamp trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.error(f"Bitstamp get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        pair_lower = pair.lower()
        url = f"https://www.bitstamp.net/api/v2/ticker/{pair_lower}/"
        try:
            async with session.get(url) as response:
                data = await response.json()
                price = float(data.get("last", 0))
                logging.info(f"Bitstamp price for {pair}: {price}")
                return price
        except Exception as e:
            logging.error(f"Bitstamp get_price error for {pair}: {e}")
            return None
