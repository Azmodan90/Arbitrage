import aiohttp
import logging
from exchanges.exchange import Exchange

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
                # Używamy pola "url_symbol" i konwertujemy do wielkich liter
                pairs = [item.get("url_symbol", "").upper() for item in data if item.get("url_symbol")]
                return pairs
        except Exception as e:
            logging.exception(f"Bitstamp get_trading_pairs error: {e}")
            return []

    async def get_price(self, symbol: str, session: aiohttp.ClientSession) -> float:
        pair = symbol.lower()
        url = f"{self.BASE_URL}/api/v2/ticker/{pair}/"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitstamp get_price HTTP error: {response.status} for {symbol}")
                    return 0.0
                data = await response.json()
                return float(data.get("last", 0))
        except Exception as e:
            logging.exception(f"Bitstamp get_price error for {symbol}: {e}")
            return 0.0
