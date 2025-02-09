import os
import ccxt
import json
import logging
import itertools
import requests
from dotenv import load_dotenv

# Konfiguracja logowania: logowanie do konsoli oraz do pliku "arbitrage.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("arbitrage.log", encoding="utf-8")
    ]
)

logging.info("Program weryfikacji wspólnych aktywów dla każdej pary giełd został uruchomiony.")

# Załaduj zmienne środowiskowe z pliku .env
load_dotenv()

# Konfiguracja giełd – pobieramy klucze API z pliku .env
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

# Inicjalizacja obiektów giełdowych przy użyciu CCXT
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
    """
    Normalizuje symbol – zamienia myślniki na ukośniki i konwertuje do wielkich liter.
    Np.: "BTC-USDT" -> "BTC/USDT"
    """
    return symbol.replace('-', '/').upper()

def build_exchange_market_dict(exchange: ccxt.Exchange) -> dict:
    """
    Dla danej giełdy zwraca słownik:
       znormalizowany symbol -> {'base': base_currency, 'quote': quote_currency}
    """
    market_dict = {}
    for symbol, market in exchange.markets.items():
        norm_symbol = normalize_symbol(symbol)
        base = market.get('base', '').upper()
        quote = market.get('quote', '').upper()
        market_dict[norm_symbol] = {'base': base, 'quote': quote}
    return market_dict

# Funkcja pobierająca mapping z CoinGecko: symbol (np. "btc") -> coin id (np. "bitcoin")
def build_coingecko_mapping() -> dict:
    url = "https://api.coingecko.com/api/v3/coins/list"
    try:
        response = requests.get(url)
        coins = response.json()
        mapping = {}
        for coin in coins:
            symbol = coin.get('symbol', '').lower()
            mapping[symbol] = coin.get('id')
        logging.info(f"Pobrano mapping CoinGecko: {len(mapping)} pozycji.")
        return mapping
    except Exception as e:
        logging.error(f"Błąd przy pobieraniu mappingu z CoinGecko: {e}")
        return {}

def verify_asset_for_pair(symbol: str, market_data1: dict, market_data2: dict, coingecko_mapping: dict) -> dict:
    """
    Dla danego symbolu (aktywa) porównuje dane techniczne z dwóch giełd.
    Zwraca słownik z informacją o spójności danych (base i quote) oraz, jeśli spójne, CoinGecko id dla tokena bazowego.
    """
    base1 = market_data1.get(symbol, {}).get('base', '')
    quote1 = market_data1.get(symbol, {}).get('quote', '')
    base2 = market_data2.get(symbol, {}).get('base', '')
    quote2 = market_data2.get(symbol, {}).get('quote', '')
    
    consistent = (base1 == base2 and quote1 == quote2)
    result = {
        'consistent_base_quote': consistent,
        'base_values': [base1, base2],
        'quote_values': [quote1, quote2]
    }
    
    if consistent:
        base_token = base1.lower()
        coin_id = coingecko_mapping.get(base_token)
        result['coingecko_id'] = coin_id
        if coin_id:
            logging.info(f"{symbol}: Spójne dane: base={base1}, quote={quote1} -> CoinGecko id: {coin_id}")
        else:
            logging.warning(f"{symbol}: Spójne dane, lecz nie znaleziono CoinGecko id dla base: {base1}")
    else:
        result['coingecko_id'] = None
        logging.warning(f"{symbol}: Rozbieżność danych: base: [{base1}, {base2}], quote: [{quote1}, {quote2}]")
    
    return result

def save_data_to_file(data: dict, filename: str):
    """
    Zapisuje dane do pliku JSON.
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"Dane zapisane do pliku: {filename}")
    except Exception as e:
        logging.error(f"Błąd podczas zapisu danych do pliku {filename}: {e}")

def main():
    # Budujemy słownik rynkowy dla każdej giełdy:
    market_data_by_exchange = {}
    for exch_name, exch_obj in exchanges.items():
        try:
            market_data = build_exchange_market_dict(exch_obj)
            market_data_by_exchange[exch_name] = market_data
            logging.info(f"{exch_name}: przetworzono dane dla {len(market_data)} symboli.")
        except Exception as e:
            logging.error(f"Błąd przy przetwarzaniu danych dla {exch_name}: {e}")
    
    # Tworzymy mapping z CoinGecko
    coingecko_mapping = build_coingecko_mapping()

    # Dla każdej pary giełd obliczamy wspólne aktywa i weryfikujemy dane techniczne
    common_assets_by_pair = {}  # klucz: "ex1-ex2", wartość: { symbol: weryfikacja }
    
    for (ex1, data1), (ex2, data2) in itertools.combinations(market_data_by_exchange.items(), 2):
        pair_key = f"{ex1}-{ex2}"
        # Obliczamy wspólny zbiór symboli
        common_symbols = set(data1.keys()).intersection(set(data2.keys()))
        logging.info(f"{pair_key}: znaleziono {len(common_symbols)} wspólnych aktywów.")
        pair_verification = {}
        for symbol in sorted(common_symbols):
            verification = verify_asset_for_pair(symbol, data1, data2, coingecko_mapping)
            pair_verification[symbol] = verification
        common_assets_by_pair[pair_key] = pair_verification

    # Zapisujemy wyniki do pliku JSON
    save_data_to_file(common_assets_by_pair, "common_assets_by_pair_verified.json")

    # Opcjonalnie: wyświetlamy wyniki na konsoli
    for pair, verif_data in common_assets_by_pair.items():
        print(f"\nPara giełd: {pair}")
        for symbol, result in verif_data.items():
            print(f"  {symbol}: spójność={result['consistent_base_quote']}, base={result['base_values']}, quote={result['quote_values']}, CoinGecko id={result.get('coingecko_id')}")
    
    logging.info("Program zakończył działanie pomyślnie.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"Krytyczny błąd: {e}")
