import aiohttp
import logging
from exchanges.exchange import Exchange

class BinanceExchange(Exchange):
    BASE_URL = "https://api.binance.com"

    def __init__(self, api_key, secret):
        self.api_key = api_key
        self.secret = secret
        # Tworzymy własną sesję, którą będziemy zamykać później
        self.session = aiohttp.ClientSession()

    async def get_trading_pairs(self):
        url = f"{self.BASE_URL}/api/v3/exchangeInfo"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Binance get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                pairs = []
                for item in data.get("symbols", []):
                    if item.get("status") == "TRADING":
                        pairs.append(item["symbol"].upper())
                return pairs
        except Exception as e:
            logging.exception(f"Binance get_trading_pairs error: {e}")
            return []

    async def get_price(self, symbol: str) -> float:
        url = f"{self.BASE_URL}/api/v3/ticker/price?symbol={symbol}"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Binance get_price HTTP error: {response.status} for {symbol}")
                    return 0.0
                data = await response.json()
                return float(data.get("price", 0))
        except Exception as e:
            logging.exception(f"Binance get_price error for {symbol}: {e}")
            return 0.0

    async def close(self):
        await self.session.close()
