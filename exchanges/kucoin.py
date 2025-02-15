import aiohttp
import logging
from exchanges.exchange import Exchange

class KucoinExchange(Exchange):
    BASE_URL = "https://api.kucoin.com"

    def __init__(self, api_key, secret):
        self.api_key = api_key
        self.secret = secret
        # Utworzenie własnej sesji
        self.session = aiohttp.ClientSession()

    async def get_trading_pairs(self):
        url = f"{self.BASE_URL}/api/v1/symbols"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Kucoin get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                pairs = []
                # Przykładowa struktura: lista symboli w data["data"]
                for item in data.get("data", []):
                    if item.get("enableTrading"):
                        # Zakładamy, że symbol jest przechowywany w polu "symbol" w formacie "BTC-USDT"
                        # Możesz usunąć znak '-' lub pozostawić go, w zależności od potrzeb normalizacji.
                        pairs.append(item["symbol"].replace("-", "").upper())
                return pairs
        except Exception as e:
            logging.exception(f"Kucoin get_trading_pairs error: {e}")
            return []

    async def get_price(self, symbol: str) -> float:
        # Kucoin oczekuje symbolu w formacie z myślnikiem, np. "BTC-USDT"
        # Jeśli symbol przekazany jest bez myślnika, dodajemy go – zakładamy, że długość symbolu to 6 znaków (BTC+USDT)
        if len(symbol) == 6:
            symbol_formatted = symbol[:3] + "-" + symbol[3:]
        else:
            symbol_formatted = symbol
        url = f"{self.BASE_URL}/api/v1/market/orderbook/level1?symbol={symbol_formatted}"
        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Kucoin get_price HTTP error: {response.status} for {symbol_formatted}")
                    return 0.0
                data = await response.json()
                return float(data.get("data", {}).get("price", 0))
        except Exception as e:
            logging.exception(f"Kucoin get_price error for {symbol_formatted}: {e}")
            return 0.0

    async def close(self):
        await self.session.close()
