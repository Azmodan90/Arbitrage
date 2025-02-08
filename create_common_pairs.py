import os
import asyncio
import aiohttp
import logging
import json
import itertools
from dotenv import load_dotenv
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange
# from exchanges.coinbase import CoinbaseExchange  # opcjonalnie
from utils import normalize_symbol

load_dotenv()

# Upewnij się, że folder log istnieje
LOG_DIR = "log"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)

# Mapowanie dostępnych giełd: klucz -> (nazwa, instancja)
EXCHANGE_OPTIONS = {
    "1": ("BinanceExchange", BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))),
    "2": ("BitgetExchange", BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))),
    "3": ("BitstampExchange", BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))),
    "4": ("KucoinExchange", KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET")))
    # "5": ("CoinbaseExchange", CoinbaseExchange(api_key=os.getenv("COINBASE_API_KEY"), secret=os.getenv("COINBASE_SECRET")))
}

# Lista wyjątków – dla każdej konfiguracji giełd (np. "BinanceExchange-BitgetExchange")
# określamy symbole, które mają zostać pominięte przy tworzeniu wspólnych par.
EXCEPTIONS = {
    "BinanceExchange-BitgetExchange": ["XXX", "YYY"],  # przykładowe wyjątki – uzupełnij wg potrzeb
    "BinanceExchange-BitstampExchange": [],
    "BinanceExchange-KucoinExchange": [],
    "BitgetExchange-BitstampExchange": [],
    "BitgetExchange-KucoinExchange": [],
    "BitstampExchange-KucoinExchange": []
}

async def create_all_common_pairs():
    """
    Pobiera listy dostępnych par (rynek spot) dla każdej giełdy tylko raz,
    a następnie wylicza wspólne pary dla każdej możliwej kombinacji giełd.
    Klucz wspólnej pary to znormalizowany symbol (uzyskany przez rozszerzoną funkcję normalize_symbol),
    a wartość to krotka oryginalnych symboli z danej giełdy.
    Przed zapisem do pliku 'common_pairs_all.json' usuwane są pary, których znormalizowany symbol znajduje się na liście wyjątków.
    """
    common_pairs_all = {}
    trading_pairs_cache = {}

    async with aiohttp.ClientSession() as session:
        # Pobierz listy par dla każdej giełdy tylko raz
        for key, (name, exch) in EXCHANGE_OPTIONS.items():
            logging.info(f"Pobieranie par dla {name}")
            pairs = await exch.get_trading_pairs(session)
            trading_pairs_cache[name] = pairs

        # Iteruj po wszystkich kombinacjach dwóch giełd
        for ((key1, (name1, _)), (key2, (name2, _))) in itertools.combinations(EXCHANGE_OPTIONS.items(), 2):
            config_key = f"{name1}-{name2}"
            logging.info(f"Przetwarzanie konfiguracji: {config_key}")
            pairs1 = trading_pairs_cache.get(name1, [])
            pairs2 = trading_pairs_cache.get(name2, [])

            # Tworzymy mapowanie: klucz – znormalizowany symbol, wartość – oryginalny symbol
            mapping1 = {normalize_symbol(sym, name1): sym for sym in pairs1}
            mapping2 = {normalize_symbol(sym, name2): sym for sym in pairs2}

            common_norm = set(mapping1.keys()) & set(mapping2.keys())
            common_list = [(mapping1[norm], mapping2[norm], norm) for norm in common_norm]

            # Filtrowanie – usuwamy te symbole, które znajdują się na liście wyjątków dla danej konfiguracji
            exceptions = EXCEPTIONS.get(config_key, [])
            common_list = [tup for tup in common_list if tup[2] not in exceptions]

            common_pairs_all[config_key] = common_list
            logging.info(f"Konfiguracja {config_key}: znaleziono {len(common_list)} wspólnych par po uwzględnieniu wyjątków.")

    filename = "common_pairs_all.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(common_pairs_all, f, ensure_ascii=False, indent=4)
    print(f"Wszystkie wspólne pary zapisane w {filename}")

if __name__ == "__main__":
    try:
        asyncio.run(create_all_common_pairs())
    except Exception as e:
        logging.exception(f"Błąd podczas tworzenia listy wspólnych par: {e}")
