# exchanges/binance.py
import aiohttp
import logging
from .exchange import Exchange

class BinanceExchange(Exchange):
    BASE_URL = "https://api.binance.com"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = f"{self.BASE_URL}/api/v3/exchangeInfo"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Binance get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                pairs = []
                for item in data.get("symbols", []):
                    if item.get("status") == "TRADING":
                        pairs.append({
                            "symbol": item["symbol"],
                            "base": item.get("baseAsset"),
                            "quote": item.get("quoteAsset")
                        })
                logging.info(f"Binance trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.exception(f"Binance get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        url = f"{self.BASE_URL}/api/v3/ticker/price?symbol={pair}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Binance get_price HTTP error: {response.status} for {pair}")
                    return None
                data = await response.json()
                price = float(data.get("price", 0))
                logging.info(f"Binance price for {pair}: {price}")
                return price
        except Exception as e:
            logging.exception(f"Binance get_price error for {pair}: {e}")
            return None
