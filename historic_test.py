import os
import ccxt
import json
import logging
import itertools
from dotenv import load_dotenv

# Załaduj zmienne środowiskowe z pliku .env
load_dotenv()

# Konfiguracja logowania: logowanie do konsoli oraz do pliku "arbitrage.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("arbitrage.log", encoding="utf-8")
    ]
)

logging.info("Program do sprawdzania danych historycznych został uruchomiony.")

# Funkcja normalizująca symbol – zamienia myślniki na ukośniki oraz konwertuje do wielkich liter
def normalize_symbol(symbol: str) -> str:
    return symbol.replace('-', '/').upper()

# Funkcja ładująca zapisane wcześniej aktywa z pliku JSON
def load_assets(filename: str = "available_assets.json") -> dict:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info(f"Pobrano dane z pliku: {filename}")
        return data
    except Exception as e:
        logging.error(f"Błąd przy wczytywaniu danych z {filename}: {e}")
        return {}

# Funkcja obliczająca zbiór wspólnych aktywów (intersection) ze słownika giełdowych list symboli
def get_common_assets(assets: dict) -> set:
    all_sets = []
    for exchange, symbols in assets.items():
        # Upewnij się, że symbole są znormalizowane
        normalized = {normalize_symbol(symbol) for symbol in symbols}
        all_sets.append(normalized)
    if all_sets:
        common = set.intersection(*all_sets)
        logging.info(f"Znaleziono {len(common)} wspólnych aktywów na wszystkich giełdach.")
        return common
    return set()

# Funkcja pobierająca historyczne dane OHLCV dla danego symbolu z wybranej giełdy
def fetch_historical_data(exchange: ccxt.Exchange, symbol: str, timeframe: str = '1d', limit: int = 30) -> list:
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        logging.info(f"Pobrano dane historyczne dla {symbol}: {len(data)} świec.")
        return data
    except Exception as e:
        logging.error(f"Błąd przy pobieraniu danych dla {symbol}: {e}")
        return []

# Funkcja zapisująca dane do pliku JSON
def save_data_to_file(data: dict, filename: str = "historical_data.json"):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"Dane historyczne zapisane do pliku: {filename}")
    except Exception as e:
        logging.error(f"Błąd podczas zapisu danych do pliku {filename}: {e}")

def main():
    # Wczytaj dane z pliku z aktywami
    assets_data = load_assets("available_assets.json")
    if not assets_data:
        logging.error("Brak danych o aktywach. Kończenie programu.")
        return

    # Oblicz wspólne aktywa (intersection) ze wszystkich giełd
    common_assets = get_common_assets(assets_data)
    if not common_assets:
        logging.warning("Nie znaleziono wspólnych aktywów.")
        return

    # Inicjalizujemy giełdę Binance – użyjemy jej do pobrania danych historycznych
    try:
        binance = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET'),
        })
        binance.load_markets()
        logging.info("Inicjalizacja Binance zakończona.")
    except Exception as e:
        logging.error(f"Błąd przy inicjalizacji Binance: {e}")
        return

    # Słownik do przechowywania danych historycznych dla każdego symbolu
    historical_data = {}

    # Dla każdego wspólnego aktywa pobieramy dane historyczne z Binance
    for symbol in sorted(common_assets):
        logging.info(f"Przetwarzanie symbolu: {symbol}")
        ohlcv = fetch_historical_data(binance, symbol, timeframe='1d', limit=30)
        # Dane zapiszemy jako listę [timestamp, open, high, low, close, volume]
        historical_data[symbol] = ohlcv

    # Zapisz dane historyczne do pliku JSON
    save_data_to_file(historical_data, filename="historical_data.json")

    # Opcjonalnie: wypisz na konsolę przykładowe dane
    for symbol, data in historical_data.items():
        print(f"\n{symbol}:")
        for candle in data:
            # Zamiana timestamp na czytelną datę (opcjonalnie)
            print(candle)

if __name__ == "__main__":
    try:
        main()
        logging.info("Program zakończył działanie pomyślnie.")
    except Exception as e:
        logging.critical(f"Krytyczny błąd: {e}")
