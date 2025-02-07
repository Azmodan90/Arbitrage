# exchanges/bitget.py

import aiohttp
import logging
from exchanges.exchange import Exchange

class BitgetExchange(Exchange):
    BASE_URL = "https://api.bitget.com"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        """
        Pobiera listę dostępnych par dla rynku spot z Bitget.
        Używamy endpointu zgodnego z dokumentacją:
          GET /api/spot/v1/public/products
        """
        url = f"{self.BASE_URL}/api/spot/v1/public/products"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                if data.get("code") != "00000":
                    logging.error(f"Bitget get_trading_pairs API error: {data.get('msg')}")
                    return []
                pairs = []
                for item in data.get("data", []):
                    symbol = item.get("symbol")
                    if symbol:
                        pairs.append(symbol)
                return pairs
        except Exception as e:
            logging.exception("Bitget get_trading_pairs exception", exc_info=e)
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        """
        Pobiera bieżącą cenę dla podanej pary z Bitget.
        Używamy endpointu:
          GET /api/spot/v1/market/ticker?symbol=<pair>
        Jeśli API nie zwróci pola "last", to używamy pola "close".
        """
        # Upewnij się, że symbol ma sufiks _SPBL – jeśli nie, dopisz go
        if not pair.endswith("_SPBL"):
            pair = f"{pair}_SPBL"
        url = f"{self.BASE_URL}/api/spot/v1/market/ticker?symbol={pair}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_price HTTP error: {response.status} for {pair}")
                    return 0.0
                data = await response.json()
                if data.get("code") != "00000":
                    logging.error(f"Bitget get_price API error: {data.get('msg')} for {pair}")
                    return 0.0
                data_field = data.get("data", {})
                # Jeśli nie ma pola "last", spróbuj użyć pola "close"
                price_str = data_field.get("last") or data_field.get("close")
                if price_str is None:
                    logging.error(f"Bitget get_price: brak pola 'last' lub 'close' dla {pair}. Pełna odpowiedź: {data}")
                    return 0.0
                return float(price_str)
        except Exception as e:
            logging.exception(f"Bitget get_price exception for {pair}: {e}")
            return 0.0
