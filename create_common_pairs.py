# create_common_pairs.py
import os
import asyncio
import aiohttp
import logging
import json
import itertools
from dotenv import load_dotenv

# Import klas giełdowych oraz funkcji do normalizacji symboli
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange
# from exchanges.coinbase import CoinbaseExchange  # opcjonalnie
from utils import normalize_symbol

load_dotenv()

# Mapowanie dostępnych giełd: numer -> (nazwa, instancja)
EXCHANGE_OPTIONS = {
    "1": ("BinanceExchange", BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))),
    "2": ("BitgetExchange", BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))),
    "3": ("BitstampExchange", BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))),
    "4": ("KucoinExchange", KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET")))
    # "5": ("CoinbaseExchange", CoinbaseExchange(api_key=os.getenv("COINBASE_API_KEY"), secret=os.getenv("COINBASE_SECRET")))
}

def parse_pair(raw, exchange_name: str) -> dict:
    """
    Jeśli raw jest dict (np. z Binance), zwraca słownik z symbol, base, quote.
    W przeciwnym razie (raw jest stringiem) zwraca dict z tylko symbolem.
    """
    if isinstance(raw, dict):
        return {
            "symbol": raw.get("symbol"),
            "base": raw.get("base"),
            "quote": raw.get("quote")
        }
    else:
        return {
            "symbol": raw,
            "base": None,
            "quote": None
        }

async def create_all_common_pairs():
    """
    Pobiera listy dostępnych par dla każdej giełdy (rynek spot) tylko raz,
    a następnie wylicza wspólne pary dla każdej możliwej kombinacji giełd.
    Dodatkowo – jeśli dostępne są dane base/quote – weryfikuje, czy tokeny to ten sam projekt.
    Wynik zapisuje do pliku 'common_pairs_all.json' oraz loguje liczbę znalezionych par.
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
            logging.info(f"Przetwarzanie konfiguracji: {name1} - {name2}")
            pairs1 = trading_pairs_cache.get(name1, [])
            pairs2 = trading_pairs_cache.get(name2, [])
            # Tworzymy mapowanie: znormalizowany symbol -> dane (dict)
            mapping1 = {normalize_symbol(parse_pair(sym, name1)["symbol"], name1): parse_pair(sym, name1) for sym in pairs1}
            mapping2 = {normalize_symbol(parse_pair(sym, name2)["symbol"], name2): parse_pair(sym, name2) for sym in pairs2}
            # Wyliczamy wspólne klucze
            common_norm = set(mapping1.keys()) & set(mapping2.keys())
            common_list = []
            for norm in common_norm:
                info1 = mapping1[norm]
                info2 = mapping2[norm]
                # Jeśli obie giełdy dostarczyły dodatkowe dane, sprawdzamy base/quote
                if info1["base"] and info2["base"]:
                    if info1["base"] != info2["base"] or info1["quote"] != info2["quote"]:
                        # Jeśli różnią się – pomijamy tę parę
                        continue
                common_list.append((info1["symbol"], info2["symbol"], norm))
            pair_key = f"{name1}-{name2}"
            common_pairs_all[pair_key] = common_list
            logging.info(f"Konfiguracja {pair_key}: znaleziono {len(common_list)} wspólnych par.")

    filename = "common_pairs_all.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(common_pairs_all, f, ensure_ascii=False, indent=4)
    print(f"Wszystkie wspólne pary zapisane w {filename}")

if __name__ == "__main__":
    try:
        asyncio.run(create_all_common_pairs())
    except Exception as e:
        logging.exception(f"Błąd podczas tworzenia listy wspólnych par: {e}")
