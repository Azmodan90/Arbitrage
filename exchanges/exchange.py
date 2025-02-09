from abc import ABC, abstractmethod
import aiohttp

class Exchange(ABC):
    def __init__(self, api_key: str = None, secret: str = None):
        self.api_key = api_key
        self.secret = secret

    @abstractmethod
    async def get_trading_pairs(self, session: aiohttp.ClientSession) -> list:
        """
        Powinno zwracać listę symboli dostępnych na giełdzie, np. ["BTCUSDT", "ETHUSDT", ...].
        """
        pass

    @abstractmethod
    async def get_price(self, symbol: str, session: aiohttp.ClientSession) -> float:
        """
        Pobiera bieżącą cenę dla podanego symbolu.
        """
        pass
