import aiohttp
import logging
from .exchange import Exchange

class KucoinExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = "https://api.kucoin.com/api/v1/symbols"
        try:
            async with session.get(url) as response:
                data = await response.json()
                symbols = data.get("data", [])
                pairs = [item["symbol"].replace("-", "") for item in symbols if item.get("trading", False)]
                logging.info(f"Kucoin trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.error(f"Kucoin get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        if "-" not in pair:
            base = pair[:3]
            quote = pair[3:]
            pair_formatted = f"{base}-{quote}"
        else:
            pair_formatted = pair
        
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={pair_formatted}"
        try:
            async with session.get(url) as response:
                data = await response.json()
                price_str = data.get("data", {}).get("price", "0")
                price = float(price_str)
                logging.info(f"Kucoin price for {pair_formatted}: {price}")
                return price
        except Exception as e:
            logging.error(f"Kucoin get_price error for {pair_formatted}: {e}")
            return None
