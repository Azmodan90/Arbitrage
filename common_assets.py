import json
import logging
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange

# Konfiguracja logowania
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(common_assets, f, indent=4)
        logging.info(f"Lista wspólnych aktywów zapisana do pliku: {filename}")
    except Exception as e:
        logging.error(f"Błąd przy zapisywaniu do pliku {filename}: {e}")

def modify_common_assets(common_assets, remove_file="assets_to_remove.json", add_file="assets_to_add.json"):
    """
    Modyfikuje listę wspólnych aktywów na podstawie dodatkowych plików konfiguracyjnych:
      - assets_to_remove.json: zawiera mapowanie konfiguracji na listy aktywów do usunięcia,
      - assets_to_add.json: zawiera mapowanie konfiguracji na listy aktywów do dodania. 
      
    Przykładowe dane:
    assets_to_remove.json:
    {
      "kucoin-bitget": ["ARC"],
      "inny_przyklad": ["SYM1", "SYM2"]
    }
    
    assets_to_add.json:
    {
      "kucoin-bitget": [
        {
          "source": "ARCSOL",
          "dest": "ARC",
          "normalized": "ARC/USDT"
        },
        {
          "source": "ARCA",
          "dest": "ARCA",
          "normalized": "ARCA/USDT"
        }
      ]
    }
    Dla modyfikacji dla każdej konfiguracji (np. "kucoin-bitget") usuwamy aktywa z listy, których nazwy znajdują się w assets_to_remove,
    a następnie, jeśli dla danej konfiguracji w assets_to_add istnieją wpisy, dodajemy do listy wartość pola "normalized".
    """
    # Wczytanie listy aktywów do usunięcia
    try:
        with open(remove_file, "r", encoding="utf-8") as f:
            assets_to_remove = json.load(f)
        logging.info(f"Wczytano dane do usunięcia z {remove_file}.")
    except Exception as e:
        assets_to_remove = {}
        logging.warning(f"Nie udało się wczytać {remove_file}: {e}")

    # Wczytanie listy aktywów do dodania
    try:
        with open(add_file, "r", encoding="utf-8") as f:
            assets_to_add = json.load(f)
        logging.info(f"Wczytano dane do dodania z {add_file}.")
    except Exception as e:
        assets_to_add = {}
        logging.warning(f"Nie udało się wczytać {add_file}: {e}")

    # Dla każdej konfiguracji modyfikujemy listę
    for config_key in list(common_assets.keys()):
        # Usuwanie aktywów
        if config_key in assets_to_remove:
            remove_list = assets_to_remove[config_key]  # lista aktywów do usunięcia
            before = len(common_assets[config_key])
            common_assets[config_key] = [asset for asset in common_assets[config_key] if asset not in remove_list]
            after = len(common_assets[config_key])
            logging.info(f"Konfiguracja {config_key}: usunięto {before - after} aktywów.")
        # Dodawanie aktywów
        if config_key in assets_to_add:
            add_entries = assets_to_add[config_key]  # lista słowników z kluczem "normalized"
            for entry in add_entries:
                normalized = entry.get("normalized")
                if normalized and normalized not in common_assets[config_key]:
                    common_assets[config_key].append(normalized)
                    logging.info(f"Konfiguracja {config_key}: dodano aktywo {normalized}.")

    # Obsługa konfiguracji, które pojawiają się w assets_to_add, a nie występują jeszcze w common_assets
    for config_key, add_entries in assets_to_add.items():
        if config_key not in common_assets:
            common_assets[config_key] = []
            for entry in add_entries:
                normalized = entry.get("normalized")
                if normalized:
                    common_assets[config_key].append(normalized)
                    logging.info(f"Nowa konfiguracja {config_key}: dodano aktywo {normalized}.")

    return common_assets

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

    # Modyfikacja listy wspólnych aktywów na podstawie plików konfiguracyjnych
    common_assets = modify_common_assets(common_assets)

    save_common_assets(common_assets)
    for pair, assets in common_assets.items():
        logging.info(f"Para {pair} ma {len(assets)} wspólnych aktywów.")

if __name__ == '__main__':
    main()
