import os
import asyncio
import aiohttp
import json
import itertools
import logging
from dotenv import load_dotenv
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange

load_dotenv()

# Konfiguracja logowania – logi zapisywane są w pliku "app.log" w głównym folderze
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

EXCHANGE_INSTANCES = {
    "BinanceExchange": BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET")),
    "BitgetExchange": BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET")),
    "BitstampExchange": BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET")),
    "KucoinExchange": KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))
}

def load_exceptions():
    filename = "exceptions.json"
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

async def create_common_pairs():
    """
    Pobiera listy symboli z każdej giełdy i tworzy wspólne aktywa
    dla każdej pary giełd. Wynik zapisuje do pliku common_pairs.json.
    """
    common_pairs = {}
    trading_pairs = {}

    async with aiohttp.ClientSession() as session:
        for name, exchange in EXCHANGE_INSTANCES.items():
            logging.info(f"Pobieranie par dla {name}")
            pairs = await exchange.get_trading_pairs(session)
            trading_pairs[name] = set(pairs)
            logging.info(f"{name} - {len(pairs)} par")

    for (name1, pairs1), (name2, pairs2) in itertools.combinations(trading_pairs.items(), 2):
        common = pairs1 & pairs2
        key = f"{name1}-{name2}"
        exceptions = load_exceptions().get(key, [])
        common = common - set(exceptions)
        common_pairs[key] = list(common)
        logging.info(f"{key} - {len(common)} wspólnych par po usunięciu wyjątków")

    with open("common_pairs.json", "w", encoding="utf-8") as f:
        json.dump(common_pairs, f, ensure_ascii=False, indent=4)
    print("Wspólne pary zapisane w common_pairs.json")

if __name__ == "__main__":
    asyncio.run(create_common_pairs())
