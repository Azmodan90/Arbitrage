import json
import logging
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange

def get_markets(exchange_instance):
    try:
        logging.info(f"Ładowanie rynków dla: {exchange_instance.__class__.__name__}")
        markets = exchange_instance.exchange.load_markets()
        return set(markets.keys())
    except Exception as e:
        logging.error(f"Błąd przy ładowaniu rynków dla {exchange_instance.__class__.__name__}: {e}")
        return set()

def get_common_assets_for_pair(exchange1, exchange2):
    markets1 = get_markets(exchange1)
    markets2 = get_markets(exchange2)
    common = markets1.intersection(markets2)
    logging.info(f"Wspólne aktywa dla {exchange1.__class__.__name__} i {exchange2.__class__.__name__}: {len(common)} znalezione")
    return common

def save_common_assets(common_assets, filename="common_assets.json"):
    try:
        with open(filename, "w") as f:
            json.dump(common_assets, f, indent=4)
        logging.info(f"Lista wspólnych aktywów zapisana do pliku: {filename}")
    except Exception as e:
        logging.error(f"Błąd przy zapisywaniu do pliku {filename}: {e}")

def main():
    logging.info("Rozpoczynam tworzenie listy wspólnych aktywów")
    binance = BinanceExchange()
    kucoin = KucoinExchange()
    bitget = BitgetExchange()
    bitstamp = BitstampExchange()

    exchanges = {
        "binance": binance,
        "kucoin": kucoin,
        "bitget": bitget,
        "bitstamp": bitstamp
    }

    common_assets = {}
    exchange_names = list(exchanges.keys())
    for i in range(len(exchange_names)):
        for j in range(i + 1, len(exchange_names)):
            name1 = exchange_names[i]
            name2 = exchange_names[j]
            logging.info(f"Porównuję aktywa dla pary: {name1} - {name2}")
            common = list(get_common_assets_for_pair(exchanges[name1], exchanges[name2]))
            common_assets[f"{name1}-{name2}"] = common

    save_common_assets(common_assets)
    for pair, assets in common_assets.items():
        logging.info(f"Para {pair} ma {len(assets)} wspólnych aktywów.")

if __name__ == '__main__':
    main()
