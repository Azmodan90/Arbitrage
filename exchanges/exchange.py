# exchanges/exchange.py

from abc import ABC, abstractmethod
import aiohttp

class Exchange(ABC):
    def __init__(self, api_key: str, secret: str):
        self.api_key = api_key
        self.secret = secret

    @abstractmethod
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        """
        Pobiera listę dostępnych par/aktywow z giełdy.
        Powinno zwracać listę stringów, np. ["BTCUSDT", "ETHUSDT", ...]
        """
        pass

    @abstractmethod
    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        """
        Pobiera bieżącą cenę dla danego symbolu/pary.
        """
        pass
