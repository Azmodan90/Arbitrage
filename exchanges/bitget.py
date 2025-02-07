# exchanges/bitget.py
import aiohttp
import logging
from exchanges.exchange import Exchange

class BitgetExchange(Exchange):
    BASE_URL = "https://api.bitget.com"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        """
        Pobiera listę dostępnych par dla rynku spot z Bitget.
        Używamy endpointu: GET /api/spot/v1/public/products
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
        Jeśli w odpowiedzi nie ma pola 'last', próbuje użyć pola 'close'.
        """
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
                # Jeśli nie ma pola "last", spróbujmy "close"
                price_str = data.get("data", {}).get("last")
                if price_str is None:
                    price_str = data.get("data", {}).get("close")
                    if price_str is None:
                        logging.error(f"Bitget get_price: brak pola 'last' lub 'close' dla {pair}")
                        return 0.0
                price = float(price_str)
                logging.info(f"Bitget price for {pair}: {price}")
                return price
        except Exception as e:
            logging.exception(f"Bitget get_price exception for {pair}: {e}")
            return 0.0
