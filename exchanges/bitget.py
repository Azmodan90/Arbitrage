# exchanges/bitget.py

import aiohttp
import logging
from .exchange import Exchange

class BitgetExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        # Przykładowy endpoint – sprawdź dokumentację Bitget, aby dopasować URL i sposób parsowania
        url = "https://api.bitget.com/api/spot/v1/public/products"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Zakładamy, że dane są pod kluczem "data" i każdy produkt ma pole "symbol"
                pairs = [item.get("symbol", "") for item in data.get("data", []) if item.get("symbol")]
                return pairs
        except Exception as e:
            logging.error(f"Bitget get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        # Przykładowy endpoint do pobierania ticker’a – warto zweryfikować w dokumentacji Bitget
        url = f"https://api.bitget.com/api/spot/v1/market/ticker?symbol={pair}"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Zakładamy, że odpowiedź zawiera obiekt "data" z polem "last" (ostatnia cena)
                ticker = data.get("data", {})
                price = float(ticker.get("last", 0))
                return price
        except Exception as e:
            logging.error(f"Bitget get_price error for {pair}: {e}")
            return None
