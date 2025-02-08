import aiohttp
import logging
from exchanges.exchange import Exchange

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
                        pairs.append(item["symbol"].upper())
                return pairs
        except Exception as e:
            logging.exception(f"Binance get_trading_pairs error: {e}")
            return []

    async def get_price(self, symbol: str, session: aiohttp.ClientSession) -> float:
        url = f"{self.BASE_URL}/api/v3/ticker/price?symbol={symbol}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Binance get_price HTTP error: {response.status} for {symbol}")
                    return 0.0
                data = await response.json()
                return float(data.get("price", 0))
        except Exception as e:
            logging.exception(f"Binance get_price error for {symbol}: {e}")
            return 0.0
