import os
import ccxt
import json
import logging
import re
import sys
import signal
from dotenv import load_dotenv

# Obsługa przerwania (CTRL+C)
def signal_handler(sig, frame):
    logging.info("Przerwanie przez użytkownika (CTRL+C). Kończenie programu.")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Konfiguracja logowania: logowanie do konsoli oraz do pliku "verified_assets.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("verified_assets.log", encoding="utf-8")
    ]
)

logging.info("Program tworzenia listy wspólnych aktywów został uruchomiony.")

# Załaduj zmienne środowiskowe z pliku .env
load_dotenv()

# Konfiguracja giełd – pobieramy klucze API z .env
exchanges_config = {
    'binance': {
        'apiKey': os.getenv('BINANCE_API_KEY'),
        'secret': os.getenv('BINANCE_SECRET'),
    },
    'kucoin': {
        'apiKey': os.getenv('KUCOIN_API_KEY'),
        'secret': os.getenv('KUCOIN_SECRET'),
    },
    'bitget': {
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_SECRET'),
    },
    'bitstamp': {
        'apiKey': os.getenv('BITSTAMP_API_KEY'),
        'secret': os.getenv('BITSTAMP_SECRET'),
    },
}

# Inicjalizacja obiektów giełdowych
exchanges = {}
for name, config in exchanges_config.items():
    try:
        if name == 'kucoin':
            exchanges[name] = ccxt.kucoin(config)
        elif name == 'bitget':
            exchanges[name] = ccxt.bitget(config)
        elif name == 'bitstamp':
            exchanges[name] = ccxt.bitstamp(config)
        else:  # domyślnie Binance
            exchanges[name] = ccxt.binance(config)
        exchanges[name].load_markets()
        logging.info(f"Inicjalizacja giełdy {name} zakończona pomyślnie.")
    except Exception as e:
        logging.error(f"Błąd przy inicjalizacji {name}: {e}")

def normalize_symbol(symbol: str) -> str:
    """Zamienia myślniki na ukośniki i konwertuje do wielkich liter."""
    return symbol.replace('-', '/').upper()

def normalize_id(market_id: str) -> str:
    """Usuwa znaki niealfanumeryczne i konwertuje do małych liter."""
    return re.sub(r'[^a-zA-Z0-9]', '', market_id).lower() if market_id else ''

def build_exchange_market_dict(exchange: ccxt.Exchange) -> dict:
    """
    Dla danej giełdy buduje słownik:
      znormalizowany symbol -> {'base': base, 'quote': quote, 'id': normalized_id}
    """
    market_dict = {}
    for symbol, market in exchange.markets.items():
        norm_symbol = normalize_symbol(symbol)
        base = market.get('base', '').upper()
        quote = market.get('quote', '').upper()
        market_id = market.get('id', '')
        norm_market_id = normalize_id(market_id)
        market_dict[norm_symbol] = {
            'base': base,
            'quote': quote,
            'id': norm_market_id
        }
    return market_dict

def load_assets(filename: str = "available_assets.json") -> dict:
    """
    Wczytuje listę aktywów dla każdej giełdy z pliku JSON.
    """
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info(f"Pobrano dane z pliku: {filename}")
        return data
    except Exception as e:
        logging.error(f"Błąd przy wczytywaniu danych z {filename}: {e}")
        return {}

def create_verified_common_assets():
    """
    Tworzy listę wspólnych aktywów, które są spójne pod względem danych technicznych (base, quote, id)
    dla wszystkich giełd.
    """
    assets_data = load_assets("available_assets.json")
    if not assets_data:
        logging.error("Brak danych o aktywach. Kończenie programu.")
        return

    # Budujemy słownik rynkowy dla każdej giełdy
    market_data_by_exchange = {}
    for exch_name in assets_data.keys():
        if exch_name in exchanges:
            try:
                market_data_by_exchange[exch_name] = build_exchange_market_dict(exchanges[exch_name])
                logging.info(f"{exch_name}: przetworzono dane rynkowe dla {len(market_data_by_exchange[exch_name])} symboli.")
            except Exception as e:
                logging.error(f"Błąd przy przetwarzaniu danych giełdy {exch_name}: {e}")
        else:
            logging.warning(f"Giełda {exch_name} nie została zainicjalizowana.")

    # Obliczamy wspólne aktywa – przecięcie symboli ze wszystkich giełd
    all_sets = []
    for exch, data in market_data_by_exchange.items():
        all_sets.append(set(data.keys()))
    if not all_sets:
        logging.error("Nie znaleziono żadnych danych rynkowych.")
        return

    common_assets = set.intersection(*all_sets)
    logging.info(f"Znaleziono {len(common_assets)} wspólnych aktywów (przed weryfikacją spójności).")

    # Weryfikacja spójności danych technicznych dla każdego symbolu
    verified_assets = {}
    for symbol in common_assets:
        bases = set()
        quotes = set()
        ids = set()
        for exch, data in market_data_by_exchange.items():
            asset = data.get(symbol)
            if asset:
                bases.add(asset.get('base', ''))
                quotes.add(asset.get('quote', ''))
                ids.add(asset.get('id', ''))
        if len(bases) == 1 and len(quotes) == 1 and len(ids) == 1:
            verified_assets[symbol] = {
                'base': list(bases)[0],
                'quote': list(quotes)[0],
                'id': list(ids)[0]
            }
        else:
            logging.warning(f"Symbol {symbol} niespójny: base={bases}, quote={quotes}, id={ids}")
    logging.info(f"Zatwierdzono {len(verified_assets)} aktywów spośród {len(common_assets)} wspólnych.")

    # Zapisujemy wyniki do pliku
    try:
        with open("verified_common_assets.json", "w", encoding="utf-8") as f:
            json.dump(verified_assets, f, ensure_ascii=False, indent=4)
        logging.info("Zapisano zweryfikowaną listę wspólnych aktywów do pliku 'verified_common_assets.json'.")
    except Exception as e:
        logging.error(f"Błąd podczas zapisu zweryfikowanych danych: {e}")

if __name__ == "__main__":
    try:
        create_verified_common_assets()
        logging.info("Program tworzenia listy wspólnych aktywów zakończył działanie pomyślnie.")
    except Exception as e:
        logging.critical(f"Krytyczny błąd: {e}")
