# exchanges/exchange.py
from abc import ABC, abstractmethod
import aiohttp

class Exchange(ABC):
    def __init__(self, api_key: str = None, secret: str = None):
        self.api_key = api_key
        self.secret = secret

    @abstractmethod
    async def get_trading_pairs(self, session: aiohttp.ClientSession) -> list:
        """
        Pobiera listę dostępnych par/aktywow z giełdy.
        """
        pass

    @abstractmethod
    async def get_price(self, pair: str, session: aiohttp.ClientSession) -> float:
        """
        Pobiera bieżącą cenę dla podanej pary.
        """
        pass
