# exchanges/kucoin.py

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
                # Usuń myślniki z symboli
                pairs = [item["symbol"].replace("-", "") for item in symbols if item.get("enableTrading", False)]
                logging.info(f"Kucoin trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.exception(f"Kucoin get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        # Jeśli symbol nie zawiera myślnika, zakładamy format np. BTCUSDT i wstawiamy myślnik.
        if "-" not in pair:
            base = pair[:3]
            quote = pair[3:]
            pair_formatted = f"{base}-{quote}"
        else:
            pair_formatted = pair

        url = f"{self.BASE_URL}/api/v1/market/orderbook/level1?symbol={pair_formatted}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Kucoin get_price HTTP error: {response.status} for {pair_formatted}")
                    return None
                data = await response.json()
                if data is None or data.get("data") is None:
                    logging.error(f"Kucoin get_price error for {pair_formatted}: brak danych. Pełna odpowiedź: {data}")
                    return None
                price_str = data.get("data", {}).get("price", "0")
                try:
                    price = float(price_str)
                except ValueError:
                    logging.error(f"Kucoin get_price error for {pair_formatted}: nieprawidłowa cena {price_str}")
                    return None
                logging.info(f"Kucoin price for {pair_formatted}: {price}")
                return price
        except Exception as e:
            logging.exception(f"Kucoin get_price error for {pair_formatted}: {e}")
            return None
