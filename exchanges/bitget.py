import aiohttp
import logging
import asyncio
from exchanges.exchange import Exchange

class BitgetExchange(Exchange):
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        # Przykładowa implementacja – należy dostosować do rzeczywistego API Bitget.
        url = "https://api.bitget.com/api/spot/v1/market/symbols"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                # Załóżmy, że lista symboli znajduje się w data["data"]
                return data.get("data", [])
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Bitget get_trading_pairs error: {e}")
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        # Budujemy URL wykorzystując przekazany (już znormalizowany) symbol
        url = f"https://api.bitget.com/api/spot/v1/market/ticker?symbol={pair}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_price HTTP error: {response.status} for {pair}")
                    return None
                data = await response.json()
                # Załóżmy, że cena znajduje się pod data["data"]["last"]
                price = float(data["data"]["last"])
                return price
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Bitget get_price error for {pair}: {e}")
            return None
