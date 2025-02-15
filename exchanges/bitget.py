import aiohttp
import logging
from exchanges.exchange import Exchange

class BitgetExchange(Exchange):
    BASE_URL = "https://api.bitget.com"  # Podstawowy URL – dostosuj do aktualnej dokumentacji

    def __init__(self, api_key, secret):
        self.api_key = api_key
        self.secret = secret
        # Utworzenie własnej sesji, która zostanie zamknięta przez close()
        self.session = aiohttp.ClientSession()

    async def get_trading_pairs(self):
        url = f"{self.BASE_URL}/api/mix/v1/market/symbols"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                pairs = []
                # Przykładowa struktura danych – dostosuj do faktycznej odpowiedzi API
                for item in data.get("data", {}).get("list", []):
                    if item.get("state") == "normal":
                        pairs.append(item["symbol"].upper())
                return pairs
        except Exception as e:
            logging.exception(f"Bitget get_trading_pairs error: {e}")
            return []

    async def get_price(self, symbol: str) -> float:
        url = f"{self.BASE_URL}/api/mix/v1/market/ticker?symbol={symbol}"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_price HTTP error: {response.status} for {symbol}")
                    return 0.0
                data = await response.json()
                return float(data.get("data", {}).get("last", 0))
        except Exception as e:
            logging.exception(f"Bitget get_price error for {symbol}: {e}")
            return 0.0

    async def close(self):
        await self.session.close()
