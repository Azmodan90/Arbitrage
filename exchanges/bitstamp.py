import aiohttp
import logging
from exchanges.exchange import Exchange

class BitstampExchange(Exchange):
    BASE_URL = "https://www.bitstamp.net/api"

    def __init__(self, api_key, secret):
        self.api_key = api_key
        self.secret = secret
        # Utworzenie własnej sesji
        self.session = aiohttp.ClientSession()

    async def get_trading_pairs(self):
        url = f"{self.BASE_URL}/v2/trading-pairs-info/"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitstamp get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                pairs = []
                # Dostosuj pętlę do struktury danych zwracanej przez API Bitstamp
                for item in data:
                    if item.get("trading") == "Enabled":
                        pairs.append(item["url_symbol"].upper())
                return pairs
        except Exception as e:
            logging.exception(f"Bitstamp get_trading_pairs error: {e}")
            return []

    async def get_price(self, symbol: str) -> float:
        # API Bitstamp oczekuje symbolu w formacie np. "btcusd"
        url = f"{self.BASE_URL}/v2/ticker/{symbol.lower()}/"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitstamp get_price HTTP error: {response.status} for {symbol}")
                    return 0.0
                data = await response.json()
                return float(data.get("last", 0))
        except Exception as e:
            logging.exception(f"Bitstamp get_price error for {symbol}: {e}")
            return 0.0

    async def close(self):
        await self.session.close()
