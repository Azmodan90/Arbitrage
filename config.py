import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    # Klucze API – upewnij się, że zmienne środowiskowe są ustawione
    "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY"),
    "BINANCE_SECRET": os.getenv("BINANCE_SECRET"),
    "KUCOIN_API_KEY": os.getenv("KUCOIN_API_KEY"),
    "KUCOIN_SECRET": os.getenv("KUCOIN_SECRET"),
    "BITGET_API_KEY": os.getenv("BITGET_API_KEY"),
    "BITGET_SECRET": os.getenv("BITGET_SECRET"),
    "BITSTAMP_API_KEY": os.getenv("BITSTAMP_API_KEY"),
    "BITSTAMP_SECRET": os.getenv("BITSTAMP_SECRET"),
    
    # Dozwolone waluty (quote) – tylko symbole z tymi quote będą rozpatrywane
    "ALLOWED_QUOTES": ["USDT", "EUR"],
    
    # Domyślna kwota inwestycji (w USDT)
    "INVESTMENT_AMOUNT": 200,
    
    # Dla których quote należy przeliczać inwestycję (z USDT) na jednostki danej waluty
    "CONVERT_INVESTMENT": {
         "BTC": False,
         "ETH": False
         # Dodaj inne, jeśli potrzebujesz
    },
    
    # Filtracja aktywów o niskiej płynności przy tworzeniu listy wspólnych aktywów
    "FILTER_LOW_LIQUIDITY": True,
    
    # Minimalne wymagane wolumeny (sumarycznie z pierwszych N pozycji order booka) dla danego quote
    "MIN_LIQUIDITY": {
         "USDT": 200,   # np. 1000 USDT wolumenu
         "EUR": 200,      # np. 50 EUR wolumenu
         "BTC": 0.002    # np. 0.05 BTC wolumenu
    },
    
    # Liczba pierwszych poziomów order booka, z których sumujemy wolumen
    "LIQUIDITY_LEVELS_TO_CHECK": 10,
    
    # Ustawienia arbitrażu:
   
    # Minimalny procentowy zysk, przy którym okazja jest rozpatrywana
    "ARBITRAGE_THRESHOLD": 1,
    
    # Jeśli procentowy zysk przekracza tę wartość (np. 100%), okazja jest traktowana jako absurdalna i ignorowana
    "ABSURD_THRESHOLD": 100,
    
    # liczba poziomów order booka do agregacji
    "ORDERBOOK_LEVELS": 10
}
