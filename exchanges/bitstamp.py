# exchanges/bitstamp.py
import aiohttp
import logging
from .exchange import Exchange

class BitstampExchange(Exchange):
    BASE_URL = "https://www.bitstamp.net"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = f"{self.BASE_URL}/api/v2/trading-pairs-info/"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitstamp get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                pairs = [item.get("url_symbol", "").upper() for item in data if item.get("url_symbol")]
                logging.info(f"Bitstamp trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.exception(f"Bitstamp get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        pair_lower = pair.lower()
        url = f"{self.BASE_URL}/api/v2/ticker/{pair_lower}/"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitstamp get_price HTTP error: {response.status} for {pair}")
                    return None
                data = await response.json()
                price = float(data.get("last", 0))
                logging.info(f"Bitstamp price for {pair}: {price}")
                return price
        except Exception as e:
            logging.exception(f"Bitstamp get_price error for {pair}: {e}")
            return None
