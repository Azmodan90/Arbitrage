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

def should_remove(asset, remove_list):
    """
    Sprawdza, czy dany asset powinien zostać usunięty.
    Usuwamy asset, jeśli:
      - asset dokładnie równa się wartości z remove_list, lub
      - asset zaczyna się od wartości z remove_list plus separator ("/")
    """
    for r in remove_list:
        if isinstance(asset, dict):
            # Jeśli asset jest słownikiem, sprawdzamy wartość 'normalized'
            asset_val = asset.get("normalized", "")
        else:
            asset_val = asset
        if asset_val == r or asset_val.startswith(r + "/"):
            return True
    return False

def modify_common_assets(common_assets, remove_file="assets_to_remove.json", add_file="assets_to_add.json"):
    """
    Modyfikuje listę wspólnych aktywów na podstawie dodatkowych plików konfiguracyjnych:
      - assets_to_remove.json: zawiera mapowanie konfiguracji na listy aktywów do usunięcia,
      - assets_to_add.json: zawiera mapowanie konfiguracji na listy aktywów do dodania.
    
    Przykładowe dane:
    assets_to_remove.json:
    {
      "kucoin-bitget": ["ARC"],
      "binance-kucoin": ["ACE/USDT"]
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
      ],
      "binance-kucoin": [
        {
          "source": "ACE",
          "dest": "kACE",
          "normalized": "kACE/USDT"
        }
      ],
      "bitget-binance": [
        {
          "source": "TSTBSC",
          "dest": "TST",
          "normalized": "TST/USDT"
        }
      ]
    }
    
    Dla każdej konfiguracji:
      - Usuwamy te elementy, dla których should_remove() zwróci True,
      - Następnie dla wpisów z assets_to_add dodajemy obiekt (słownik) – jeśli nie ma już wpisu o takim polu "normalized".
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

    # Modyfikacja listy dla każdej konfiguracji
    for config_key in list(common_assets.keys()):
        # Usuwanie
        if config_key in assets_to_remove:
            remove_list = assets_to_remove[config_key]
            before = len(common_assets[config_key])
            common_assets[config_key] = [asset for asset in common_assets[config_key] if not should_remove(asset, remove_list)]
            after = len(common_assets[config_key])
            logging.info(f"Konfiguracja {config_key}: usunięto {before - after} aktywów.")
        # Dodawanie – tu dodajemy obiekty, nie tylko stringi
        if config_key in assets_to_add:
            add_entries = assets_to_add[config_key]
            for entry in add_entries:
                normalized = entry.get("normalized")
                # Sprawdzamy, czy w liście już jest element (jako string lub dict) z tym samym normalized
                exists = False
                for asset in common_assets[config_key]:
                    if isinstance(asset, dict):
                        if asset.get("normalized") == normalized:
                            exists = True
                            break
                    else:
                        if asset == normalized:
                            exists = True
                            break
                if normalized and not exists:
                    common_assets[config_key].append(entry)
                    logging.info(f"Konfiguracja {config_key}: dodano aktywo {entry}.")
    # Obsługa konfiguracji, które pojawiają się w assets_to_add, a nie w common_assets
    for config_key, add_entries in assets_to_add.items():
        if config_key not in common_assets:
            common_assets[config_key] = []
            for entry in add_entries:
                normalized = entry.get("normalized")
                if normalized:
                    common_assets[config_key].append(entry)
                    logging.info(f"Nowa konfiguracja {config_key}: dodano aktywo {entry}.")
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
