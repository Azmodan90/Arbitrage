import os
import ccxt
import json
import logging
import itertools
from dotenv import load_dotenv

# Ładujemy zmienne środowiskowe
load_dotenv()

# Konfiguracja logowania: logujemy zarówno na konsolę, jak i do pliku "arbitrage_opportunities.log"
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("arbitrage_opportunities.log", encoding="utf-8")
    ]
)

logging.info("Program wyszukiwania okazji arbitrażowych został uruchomiony.")

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
        # Ładujemy rynki – potrzebne do prawidłowego działania fetch_ticker
        exchanges[name].load_markets()
        logging.info(f"Inicjalizacja giełdy {name} zakończona.")
    except Exception as e:
        logging.error(f"Błąd przy inicjalizacji {name}: {e}")

# Przykładowa struktura opłat (fee)
fees = {
    'binance': 0.001,
    'kucoin': 0.001,
    'bitget': 0.001,
    'bitstamp': 0.0025,
}

# Funkcja normalizująca symbol – zamienia myślniki na ukośniki oraz konwertuje do wielkich liter
def normalize_symbol(symbol: str) -> str:
    return symbol.replace('-', '/').upper()

# Funkcja ładująca listę wspólnych aktywów dla każdej pary giełd z pliku JSON
def load_common_assets(filename: str = "common_assets_by_pair.json") -> dict:
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logging.info(f"Pobrano listę wspólnych aktywów z {filename}")
        return data
    except Exception as e:
        logging.error(f"Błąd przy wczytywaniu {filename}: {e}")
        return {}

# Funkcja pobierająca bieżący ticker dla danego symbolu na konkretnej giełdzie
def get_ticker_price(exchange: ccxt.Exchange, symbol: str) -> dict:
    try:
        ticker = exchange.fetch_ticker(symbol)
        # Zwracamy ask (cena kupna) oraz bid (cena sprzedaży)
        return {'bid': ticker.get('bid'), 'ask': ticker.get('ask')}
    except Exception as e:
        logging.error(f"Błąd przy pobieraniu tickera dla {symbol} na {exchange.id}: {e}")
        return {}

# Funkcja sprawdzająca okazję arbitrażową między dwoma giełdami dla danego symbolu
def check_arbitrage(symbol: str, ex1_name: str, ex2_name: str) -> dict:
    ex1 = exchanges[ex1_name]
    ex2 = exchanges[ex2_name]
    fee1 = fees.get(ex1_name, 0)
    fee2 = fees.get(ex2_name, 0)
    
    # Pobieramy ticker dla symbolu na obu giełdach
    ticker1 = get_ticker_price(ex1, symbol)
    ticker2 = get_ticker_price(ex2, symbol)
    
    result = {
        'symbol': symbol,
        'exchange_buy': None,
        'exchange_sell': None,
        'buy_price': None,
        'sell_price': None,
        'profit_percent': None,
        'direction': None  # "ex1->ex2" lub "ex2->ex1"
    }
    
    # Upewnijmy się, że obie giełdy zwróciły poprawne ceny
    if ticker1.get('ask') is None or ticker2.get('bid') is None:
        logging.warning(f"Brak danych tickera dla {symbol} na parze {ex1_name}-{ex2_name}")
        return None
    # Sprawdzamy kierunek: kupno na ex1, sprzedaż na ex2
    effective_buy_1 = ticker1['ask'] * (1 + fee1)
    effective_sell_2 = ticker2['bid'] * (1 - fee2)
    profit1 = effective_sell_2 - effective_buy_1
    profit_percent1 = (profit1 / effective_buy_1) * 100 if effective_buy_1 else None

    # Sprawdzamy też odwrotny kierunek: kupno na ex2, sprzedaż na ex1
    if ticker2.get('ask') is None or ticker1.get('bid') is None:
        profit2 = None
        profit_percent2 = None
    else:
        effective_buy_2 = ticker2['ask'] * (1 + fee2)
        effective_sell_1 = ticker1['bid'] * (1 - fee1)
        profit2 = effective_sell_1 - effective_buy_2
        profit_percent2 = (profit2 / effective_buy_2) * 100 if effective_buy_2 else None

    # Wybieramy kierunek o wyższym potencjale, jeśli któryś daje dodatni zysk
    opportunity = None
    if profit_percent1 is not None and profit_percent1 > 0:
        opportunity = {
            'exchange_buy': ex1_name,
            'exchange_sell': ex2_name,
            'buy_price': ticker1['ask'],
            'sell_price': ticker2['bid'],
            'profit_percent': round(profit_percent1, 2),
            'direction': f"{ex1_name} -> {ex2_name}"
        }
    if profit_percent2 is not None and profit_percent2 > 0:
        # Jeśli oba kierunki są dodatnie, wybieramy ten o wyższym procencie
        if opportunity is None or profit_percent2 > opportunity['profit_percent']:
            opportunity = {
                'exchange_buy': ex2_name,
                'exchange_sell': ex1_name,
                'buy_price': ticker2['ask'],
                'sell_price': ticker1['bid'],
                'profit_percent': round(profit_percent2, 2),
                'direction': f"{ex2_name} -> {ex1_name}"
            }
    
    return opportunity

# Funkcja zapisująca wyniki arbitrażu do pliku JSON
def save_arbitrage_opportunities(data: dict, filename: str = "arbitrage_opportunities.json"):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        logging.info(f"Zapisano okazje arbitrażowe do pliku: {filename}")
    except Exception as e:
        logging.error(f"Błąd przy zapisie do {filename}: {e}")

def main():
    # Wczytaj listę wspólnych aktywów dla każdej pary giełd
    common_assets_by_pair = load_common_assets("common_assets_by_pair.json")
    if not common_assets_by_pair:
        logging.error("Brak danych o wspólnych aktywach. Kończenie programu.")
        return

    arbitrage_opportunities = {}
    # Ustalamy minimalny próg zysku (np. 0.2%) aby zapisywać okazje
    profit_threshold = 0.2

    # Iterujemy przez każdą parę giełd
    for pair_key, symbols in common_assets_by_pair.items():
        # Zakładamy, że klucz pary jest postaci "ex1-ex2"
        try:
            ex1_name, ex2_name = pair_key.split('-')
        except Exception as e:
            logging.error(f"Błąd w parsowaniu klucza {pair_key}: {e}")
            continue

        arbitrage_opportunities[pair_key] = []
        for symbol in symbols:
            symbol = normalize_symbol(symbol)
            opp = check_arbitrage(symbol, ex1_name, ex2_name)
            if opp is not None and opp.get('profit_percent') is not None and opp['profit_percent'] >= profit_threshold:
                arbitrage_opportunities[pair_key].append(opp)
                logging.info(f"Okazja dla {symbol} ({pair_key}): kupno na {opp['exchange_buy']} po {opp['buy_price']} "
                             f"sprzedaż na {opp['exchange_sell']} po {opp['sell_price']}, zysk {opp['profit_percent']}%")
    
    # Zapisujemy wyniki do pliku JSON
    save_arbitrage_opportunities(arbitrage_opportunities, filename="arbitrage_opportunities.json")

    # Opcjonalnie: wypisujemy wyniki na konsolę
    for pair, opps in arbitrage_opportunities.items():
        print(f"\nOkazje arbitrażowe dla pary {pair}:")
        if not opps:
            print("Brak okazji spełniających próg.")
        else:
            for opp in opps:
                print(opp)

    logging.info("Program wyszukiwania okazji arbitrażowych zakończył działanie pomyślnie.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"Krytyczny błąd: {e}")
