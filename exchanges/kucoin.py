import aiohttp
import logging
from exchanges.exchange import Exchange

class KucoinExchange(Exchange):
    BASE_URL = "https://api.kucoin.com"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = f"{self.BASE_URL}/api/v1/symbols"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Kucoin get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                symbols = data.get("data", [])
                # Ujednolicamy format – usuwamy myślniki
                pairs = [item["symbol"].replace("-", "").upper() for item in symbols if item.get("enableTrading", False)]
                return pairs
        except Exception as e:
            logging.exception(f"Kucoin get_trading_pairs error: {e}")
            return []

    async def get_price(self, symbol: str, session: aiohttp.ClientSession) -> float:
        # Jeśli symbol nie zawiera myślnika, przyjmujemy, że pierwsze 3 litery to base, reszta to quote
        if "-" not in symbol:
            base = symbol[:3]
            quote = symbol[3:]
            formatted = f"{base}-{quote}"
        else:
            formatted = symbol
        url = f"{self.BASE_URL}/api/v1/market/orderbook/level1?symbol={formatted}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Kucoin get_price HTTP error: {response.status} for {formatted}")
                    return 0.0
                data = await response.json()
                price_str = data.get("data", {}).get("price", "0")
                return float(price_str)
        except Exception as e:
            logging.exception(f"Kucoin get_price error for {formatted}: {e}")
            return 0.0
