import os
import asyncio
import aiohttp
import json
import logging
from dotenv import load_dotenv
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange
# from exchanges.coinbase import CoinbaseExchange  # opcjonalnie

load_dotenv()

# Upewnij się, że folder log istnieje
LOG_DIR = "log"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Mapowanie instancji giełd – używane przy pobieraniu cen
EXCHANGE_OPTIONS = {
    "BinanceExchange": BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET")),
    "BitgetExchange": BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET")),
    "BitstampExchange": BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET")),
    "KucoinExchange": KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))
    # "CoinbaseExchange": CoinbaseExchange(api_key=os.getenv("COINBASE_API_KEY"), secret=os.getenv("COINBASE_SECRET"))
}

# Przykładowe opłaty dla poszczególnych giełd (wartości procentowe jako ułamek dziesiętny)
EXCHANGE_FEES = {
    "BinanceExchange": 0.001,   # 0.1%
    "BitgetExchange": 0.002,    # 0.2%
    "BitstampExchange": 0.005,  # 0.5%
    "KucoinExchange": 0.001     # 0.1%
}

async def fetch_price(session, exchange, symbol):
    """
    Pobiera cenę dla danego symbolu z określonej giełdy.
    Zakładamy, że obiekt exchange posiada metodę get_price(session, symbol).
    """
    try:
        price = await exchange.get_price(session, symbol)
        return price
    except Exception as e:
        logging.error(f"Błąd pobierania ceny {symbol} na {exchange.__class__.__name__}: {e}")
        return None

async def find_arbitrage_opportunities():
    """
    Ładuje listę wspólnych par z pliku common_pairs_all.json.
    Dla każdej konfiguracji giełd pobiera ceny aktywów i uwzględniając opłaty,
    sprawdza, czy istnieje okazja arbitrażu (kupno taniej na jednej giełdzie i sprzedaż drożej na drugiej).
    Wykryte okazje loguje.
    """
    filename = "common_pairs_all.json"
    if not os.path.exists(filename):
        logging.error("Plik common_pairs_all.json nie istnieje. Najpierw uruchom opcję 1.")
        return

    with open(filename, "r", encoding="utf-8") as f:
        common_pairs_all = json.load(f)

    async with aiohttp.ClientSession() as session:
        # Przetwarzamy każdą konfigurację giełd (np. "BinanceExchange-BitgetExchange")
        for config_key, common_list in common_pairs_all.items():
            exchanges = config_key.split("-")
            if len(exchanges) != 2:
                logging.error(f"Nieprawidłowy format klucza konfiguracji: {config_key}")
                continue
            exch1_name, exch2_name = exchanges
            exch1 = EXCHANGE_OPTIONS.get(exch1_name)
            exch2 = EXCHANGE_OPTIONS.get(exch2_name)
            fee1 = EXCHANGE_FEES.get(exch1_name, 0)
            fee2 = EXCHANGE_FEES.get(exch2_name, 0)

            if not exch1 or not exch2:
                logging.error(f"Brak instancji giełdy dla konfiguracji: {config_key}")
                continue

            # Dla każdego wspólnego symbolu pobieramy ceny z obu giełd
            for symbol_pair in common_list:
                # symbol_pair: (symbol na giełdzie 1, symbol na giełdzie 2, normalized symbol)
                symbol1, symbol2, norm_symbol = symbol_pair
                price1 = await fetch_price(session, exch1, symbol1)
                price2 = await fetch_price(session, exch2, symbol2)

                if price1 is None or price2 is None:
                    continue

                # Uwzględniamy opłaty – przykładowo:
                # Kupno na giełdzie 1 (opłata zwiększa koszt), sprzedaż na giełdzie 2 (opłata zmniejsza wartość)
                effective_price1 = price1 * (1 + fee1)   # efektywna cena kupna na giełdzie 1
                effective_price2 = price2 * (1 - fee2)       # efektywna cena sprzedaży na giełdzie 2

                # Sprawdzenie okazji arbitrażu: czy kupno na jednej giełdzie + opłata jest tańsze niż sprzedaż na drugiej
                if effective_price1 < price2:
                    profit_percentage = ((price2 - effective_price1) / effective_price1) * 100
                    logging.info(f"Arbitraż: Kup {symbol1} na {exch1_name} za {price1:.4f} (efektywnie {effective_price1:.4f}) "
                                 f"i sprzedaj {symbol2} na {exch2_name} za {price2:.4f}. Zysk: {profit_percentage:.2f}%")
                elif effective_price2 < price1:
                    profit_percentage = ((price1 - effective_price2) / effective_price2) * 100
                    logging.info(f"Arbitraż: Kup {symbol2} na {exch2_name} za {price2:.4f} (efektywnie {effective_price2:.4f}) "
                                 f"i sprzedaj {symbol1} na {exch1_name} za {price1:.4f}. Zysk: {profit_percentage:.2f}%")
