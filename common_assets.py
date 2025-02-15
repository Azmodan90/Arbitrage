import json
import logging
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from config import CONFIG

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_markets_dict(exchange_instance, allowed_quotes=["USDT"]):
    try:
        logging.info(f"Ładowanie rynków dla: {exchange_instance.__class__.__name__}")
        markets = exchange_instance.exchange.load_markets()
        result = {}
        for symbol in markets:
            if "/" in symbol:
                base, quote = symbol.split("/")
                # Jeśli base jest równe quote (np. "USDT/USDT") – pomijamy
                if base == quote:
                    continue
                if quote in allowed_quotes:
                    if base not in result:
                        result[base] = symbol
        return result
    except Exception as e:
        logging.error(f"Błąd przy ładowaniu rynków dla {exchange_instance.__class__.__name__}: {e}")
        return {}

def get_common_assets_for_pair(name1, exchange1, name2, exchange2, allowed_quotes=["USDT"]):
    markets1 = get_markets_dict(exchange1, allowed_quotes)
    markets2 = get_markets_dict(exchange2, allowed_quotes)
    common_bases = set(markets1.keys()).intersection(set(markets2.keys()))
    common = {}
    for base in common_bases:
        common[base] = {name1: markets1[base], name2: markets2[base]}
    logging.info(f"Wspólne aktywa dla {name1} i {name2} (quotes={allowed_quotes}): {len(common)} znalezione")
    return common

def save_common_assets(common_assets, filename="common_assets.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(common_assets, f, indent=4)
        logging.info(f"Lista wspólnych aktywów zapisana do pliku: {filename}")
    except Exception as e:
        logging.error(f"Błąd przy zapisywaniu do pliku {filename}: {e}")

def should_remove(asset, remove_list):
    for r in remove_list:
        if asset == r or asset.startswith(r + "/"):
            return True
    return False

def modify_common_assets(common_assets, remove_file="assets_to_remove.json", add_file="assets_to_add.json"):
    try:
        with open(remove_file, "r", encoding="utf-8") as f:
            assets_to_remove = json.load(f)
        logging.info(f"Wczytano dane do usunięcia z {remove_file}.")
    except Exception as e:
        assets_to_remove = {}
        logging.warning(f"Nie udało się wczytać {remove_file}: {e}")

    try:
        with open(add_file, "r", encoding="utf-8") as f:
            assets_to_add = json.load(f)
        logging.info(f"Wczytano dane do dodania z {add_file}.")
    except Exception as e:
        assets_to_add = {}
        logging.warning(f"Nie udało się wczytać {add_file}: {e}")

    for config_key in list(common_assets.keys()):
        if config_key in assets_to_remove:
            remove_list = assets_to_remove[config_key]
            before = len(common_assets[config_key])
            common_assets[config_key] = {base: mapping for base, mapping in common_assets[config_key].items()
                                         if not should_remove(base, remove_list)}
            after = len(common_assets[config_key])
            logging.info(f"Konfiguracja {config_key}: usunięto {before - after} aktywów.")
        if config_key in assets_to_add:
            add_entries = assets_to_add[config_key]
            if config_key not in common_assets:
                common_assets[config_key] = {}
            for entry in add_entries:
                normalized = entry.get("normalized")
                if normalized and normalized not in common_assets[config_key]:
                    common_assets[config_key][normalized] = {
                        config_key.split("-")[0]: entry.get("source"),
                        config_key.split("-")[1]: entry.get("dest")
                    }
                    logging.info(f"Konfiguracja {config_key}: dodano aktywo {entry}.")
    return common_assets

def main():
    logging.info("Rozpoczynam tworzenie listy wspólnych aktywów (porównanie wyłącznie po symbolu)")
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
    names = list(exchanges.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name1 = names[i]
            name2 = names[j]
            logging.info(f"Porównuję aktywa dla pary: {name1} - {name2}")
            mapping = get_common_assets_for_pair(name1, exchanges[name1], name2, exchanges[name2], allowed_quotes=["USDT"])
            common_assets[f"{name1}-{name2}"] = mapping

    common_assets = modify_common_assets(common_assets)
    save_common_assets(common_assets)
    for pair, assets in common_assets.items():
        logging.info(f"Para {pair} ma {len(assets)} wspólnych aktywów.")

if __name__ == '__main__':
    main()
