# exchanges/bitget.py
import aiohttp
import logging
from .exchange import Exchange

class BitgetExchange(Exchange):
    BASE_URL = "https://api.bitget.com"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = f"{self.BASE_URL}/api/spot/v1/public/products"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                pairs = [item.get("symbol", "") for item in data.get("data", []) if item.get("symbol")]
                logging.info(f"Bitget trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.exception(f"Bitget get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        url = f"{self.BASE_URL}/api/spot/v1/market/ticker?symbol={pair}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_price HTTP error: {response.status} for {pair}")
                    return None
                data = await response.json()
                ticker = data.get("data", {})
                price = float(ticker.get("last", 0))
                logging.info(f"Bitget price for {pair}: {price}")
                return price
        except Exception as e:
            logging.exception(f"Bitget get_price error for {pair}: {e}")
            return None
