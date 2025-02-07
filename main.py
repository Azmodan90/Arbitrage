# main.py
import os
import asyncio
import aiohttp
import logging
import json
from dotenv import load_dotenv

# Import instancji giełd
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange
from exchanges.coinbase import CoinbaseExchange  # opcjonalnie
from utils import normalize_symbol
from arbitrage_strategy import run_arbitrage

# Konfiguracja logowania – logi wyświetlane są zarówno w konsoli, jak i zapisywane do pliku
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

load_dotenv()

# Dostępne giełdy – mapowanie opcji (numer: (nazwa, instancja))
EXCHANGE_OPTIONS = {
    "1": ("BinanceExchange", BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))),
    "2": ("BitgetExchange", BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))),
    "3": ("BitstampExchange", BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))),
    "4": ("KucoinExchange", KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))),
    "5": ("CoinbaseExchange", CoinbaseExchange(api_key=os.getenv("COINBASE_API_KEY"), secret=os.getenv("COINBASE_SECRET")))
}

# Globalny cache listy wspólnych par (klucz: (nazwa_ex1, nazwa_ex2))
COMMON_PAIRS_CACHE = {}

async def get_common_pairs(exchange1, exchange2, session: aiohttp.ClientSession):
    """
    Pobiera listy par z dwóch giełd, normalizuje symbole i zwraca przecięcie.
    Zwraca listę krotek: (oryginalny_symbol_ex1, oryginalny_symbol_ex2, normalized_symbol)
    """
    logging.info(f"Pobieranie par z {exchange1.__class__.__name__} i {exchange2.__class__.__name__}")
    pairs1 = await exchange1.get_trading_pairs(session)
    pairs2 = await exchange2.get_trading_pairs(session)
    mapping1 = {normalize_symbol(sym, exchange1.__class__.__name__): sym for sym in pairs1}
    mapping2 = {normalize_symbol(sym, exchange2.__class__.__name__): sym for sym in pairs2}
    common_norm = set(mapping1.keys()) & set(mapping2.keys())
    common_list = [(mapping1[norm], mapping2[norm], norm) for norm in common_norm]
    logging.info(f"Wspólne pary: {common_list}")
    return common_list

async def create_common_pairs():
    """
    Umożliwia wybranie dwóch giełd, pobiera wspólne pary i zapisuje listę do pliku.
    """
    print("Wybierz dwie giełdy spośród dostępnych opcji:")
    for key, (name, _) in EXCHANGE_OPTIONS.items():
        print(f"{key}: {name}")
    choice1 = input("Wybierz pierwszą giełdę (numer): ").strip()
    choice2 = input("Wybierz drugą giełdę (numer): ").strip()
    if choice1 not in EXCHANGE_OPTIONS or choice2 not in EXCHANGE_OPTIONS or choice1 == choice2:
        print("Nieprawidłowy wybór giełd.")
        return None, None, None
    exch1_name, exch1 = EXCHANGE_OPTIONS[choice1]
    exch2_name, exch2 = EXCHANGE_OPTIONS[choice2]
    async with aiohttp.ClientSession() as session:
        common_pairs = await get_common_pairs(exch1, exch2, session)
    if not common_pairs:
        print("Nie znaleziono wspólnych par.")
        return exch1_name, exch2_name, []
    filename = f"common_pairs_{exch1_name}_{exch2_name}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(common_pairs, f, ensure_ascii=False, indent=4)
    print(f"Wspólne pary zapisane w {filename}")
    COMMON_PAIRS_CACHE[(exch1_name, exch2_name)] = common_pairs
    return exch1_name, exch2_name, common_pairs

async def load_common_pairs():
    """
    Ładuje z dysku listę wspólnych par dla wybranych giełd.
    """
    print("Wybierz giełdy, dla których chcesz wczytać listę wspólnych par:")
    for key, (name, _) in EXCHANGE_OPTIONS.items():
        print(f"{key}: {name}")
    choice1 = input("Wybierz pierwszą giełdę (numer): ").strip()
    choice2 = input("Wybierz drugą giełdę (numer): ").strip()
    if choice1 not in EXCHANGE_OPTIONS or choice2 not in EXCHANGE_OPTIONS or choice1 == choice2:
        print("Nieprawidłowy wybór giełd.")
        return None, None, None
    exch1_name, exch1 = EXCHANGE_OPTIONS[choice1]
    exch2_name, exch2 = EXCHANGE_OPTIONS[choice2]
    filename = f"common_pairs_{exch1_name}_{exch2_name}.json"
    try:
        with open(filename, "r", encoding="utf-8") as f:
            common_pairs = json.load(f)
        print(f"Wczytano listę wspólnych par z {filename}")
        COMMON_PAIRS_CACHE[(exch1_name, exch2_name)] = common_pairs
        return exch1_name, exch2_name, common_pairs
    except Exception as e:
        print(f"Nie udało się wczytać listy wspólnych par: {e}")
        return exch1_name, exch2_name, []

async def run_arbitrage_program():
    """
    Uruchamia strategię arbitrażu przy użyciu zapisanej lub odświeżonej listy wspólnych par.
    """
    print("Czy chcesz użyć wcześniej zapisanej listy wspólnych par? (t/n)")
    use_cached = input().strip().lower()
    if use_cached == "t":
        exch1_name, exch2_name, common_pairs = await load_common_pairs()
    else:
        exch1_name, exch2_name, common_pairs = await create_common_pairs()
    if not common_pairs:
        print("Brak wspólnych par do analizy. Najpierw utwórz listę par.")
        return
    # Budujemy mapowanie giełd na podstawie wybranych opcji
    exchange_mapping = {}
    for key, (name, instance) in EXCHANGE_OPTIONS.items():
        if name == exch1_name or name == exch2_name:
            exchange_mapping[name] = instance
    threshold_input = input("Podaj próg arbitrażu w procentach (np. 1.0): ").strip()
    threshold = float(threshold_input) if threshold_input else 1.0
    print("Uruchamianie programu arbitrażu. Naciśnij Ctrl+C, aby przerwać.")
    try:
        while True:
            await run_arbitrage(common_pairs, exchange_mapping, threshold)
            await asyncio.sleep(10)  # 10 sekund przerwy między rundami
    except KeyboardInterrupt:
        print("Program arbitrażu został zatrzymany przez użytkownika.")

async def main():
    while True:
        print("\nWybierz opcję:")
        print("1. Utwórz/odśwież listę wspólnych par")
        print("2. Uruchom program arbitrażu")
        print("3. Wyjście")
        choice = input("Twój wybór: ").strip()
        if choice == "1":
            await create_common_pairs()
        elif choice == "2":
            await run_arbitrage_program()
        elif choice == "3":
            print("Zakończenie programu.")
            break
        else:
            print("Nieprawidłowy wybór. Spróbuj ponownie.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.exception(f"Błąd w głównym programie: {e}")
