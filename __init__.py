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
        """
        Inicjalizuje instancję giełdy z danymi uwierzytelniającymi.
        Parametry są opcjonalne – możesz je pominąć, jeśli giełda nie wymaga autoryzacji
        lub chcesz ustawić je później.

        :param api_key: Klucz API, używany do autoryzacji.
        :param secret: Tajny klucz API.
        """
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
        Pobiera bieżącą cenę dla podanej pary.
        
        :param pair: Symbol lub para aktywów, np. "BTCUSDT".
        :param session: Sesja aiohttp, używana do wykonywania zapytań HTTP.
        :return: Cena aktywa jako liczba zmiennoprzecinkowa.
        """
        pass
