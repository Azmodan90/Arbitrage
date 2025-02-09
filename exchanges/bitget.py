import aiohttp
import asyncio
import logging
from exchanges.exchange import Exchange

class BitgetExchange(Exchange):
    BASE_URL = "https://api.bitget.com"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        """
        Pobiera listę dostępnych par z Bitget. Usuwa sufiks "_SPBL" jeśli występuje.
        """
        url = f"{self.BASE_URL}/api/spot/v1/public/products"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                logging.info(f"Bitget get_trading_pairs response: {data}")
                if data.get("code") != "00000":
                    logging.error(f"Bitget API error: {data.get('msg')}")
                    return []
                pairs = []
                for item in data.get("data", []):
                    raw = item.get("symbol")
                    if raw:
                        raw = raw.upper()
                        if raw.endswith("_SPBL"):
                            raw = raw.replace("_SPBL", "")
                        pairs.append(raw)
                logging.info(f"Bitget trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.exception("Bitget get_trading_pairs exception", exc_info=e)
            return []

    async def get_price(self, symbol: str, session: aiohttp.ClientSession) -> float:
        url = f"{self.BASE_URL}/api/spot/v1/market/ticker?symbol={symbol}"
        max_retries = 3
        for attempt in range(max_retries):
            try:
                async with session.get(url) as response:
                    if response.status == 429:
                        logging.error(f"Bitget get_price HTTP error: {response.status} for {symbol} - Too Many Requests. Retry {attempt+1}/{max_retries}")
                        await asyncio.sleep(2 ** attempt)  # exponential backoff
                        continue
                    if response.status != 200:
                        logging.error(f"Bitget get_price HTTP error: {response.status} for {symbol}")
                        return 0.0
                    data = await response.json()
                    if data.get("code") != "00000":
                        logging.error(f"Bitget get_price API error: {data.get('msg')} for {symbol}")
                        return 0.0
                    price_str = data.get("data", {}).get("last")
                    if not price_str:
                        price_str = data.get("data", {}).get("close")
                        if not price_str:
                            logging.error(f"Bitget get_price: no price for {symbol}")
                            return 0.0
                    return float(price_str)
            except Exception as e:
                logging.exception(f"Bitget get_price exception for {symbol} on attempt {attempt+1}: {e}")
                await asyncio.sleep(2 ** attempt)
        return 0.0
