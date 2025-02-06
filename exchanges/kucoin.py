# exchanges/kucoin.py

import aiohttp
import logging
from .exchange import Exchange

class KucoinExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        url = "https://api.kucoin.com/api/v1/symbols"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Struktura odpowiedzi: { "code": "200000", "data": [ { "symbol": "BTC-USDT", ... }, ... ] }
                symbols = data.get("data", [])
                # Przyjmujemy, że interesują nas pary, które mają status trading (jeśli taki istnieje)
                pairs = [item["symbol"].replace("-", "") for item in symbols if item.get("trading", False)]
                logging.info(f"Kucoin trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.error(f"Kucoin get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        # Kucoin oczekuje formatu pary z myślnikiem, np. "BTC-USDT".
        # Jeśli przekazany symbol nie zawiera myślnika, zamieniamy np. "BTCUSDT" na "BTC-USDT".
        if "-" not in pair:
            base = pair[:3]
            quote = pair[3:]
            pair_formatted = f"{base}-{quote}"
        else:
            pair_formatted = pair
        
        url = f"https://api.kucoin.com/api/v1/market/orderbook/level1?symbol={pair_formatted}"
        try:
            async with session.get(url) as response:
                data = await response.json()
                # Zakładamy, że odpowiedź ma strukturę: { "code": "200000", "data": { "price": "12345.67", ... } }
                price_str = data.get("data", {}).get("price", "0")
                price = float(price_str)
                logging.info(f"Kucoin price for {pair_formatted}: {price}")
                return price
        except Exception as e:
            logging.error(f"Kucoin get_price error for {pair_formatted}: {e}")
            return None
