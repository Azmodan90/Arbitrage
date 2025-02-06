# exchanges/exchange.py

from abc import ABC, abstractmethod
import aiohttp

class Exchange(ABC):
    """
    Abstrakcyjna klasa reprezentująca interfejs giełdy.
    Wszystkie konkretne implementacje (np. Binance, Bitget, Bitstamp)
    powinny dziedziczyć po tej klasie i implementować poniższe metody.
    """
    def __init__(self, api_key: str = None, secret: str = None):
        self.api_key = api_key
        self.secret = secret

    @abstractmethod
    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        """
        Pobiera listę dostępnych par/aktywow z giełdy.
        :param session: Sesja aiohttp do wykonywania zapytań HTTP.
        :return: Lista symboli par, np. ["BTCUSDT", "ETHUSDT", ...]
        """
        pass

    @abstractmethod
    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        """
        Pobiera bieżącą cenę dla podanej pary.
        :param pair: Symbol lub para aktywów, np. "BTCUSDT".
        :param session: Sesja aiohttp do wykonywania zapytań HTTP.
        :return: Cena aktywa jako liczba zmiennoprzecinkowa.
        """
        pass
