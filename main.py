# main.py
import os
import asyncio
import aiohttp
import logging
import json
import itertools
from dotenv import load_dotenv

# Import instancji giełd – upewnij się, że struktura katalogów jest poprawna
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange
#from exchanges.coinbase import CoinbaseExchange  # opcjonalnie
from utils import normalize_symbol

# Konfiguracja logowania – logi zapisywane są zarówno do konsoli, jak i do pliku
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

load_dotenv()

# Dostępne giełdy – mapowanie: klucz (numer) -> (nazwa, instancja)
EXCHANGE_OPTIONS = {
    "1": ("BinanceExchange", BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))),
    "2": ("BitgetExchange", BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))),
    "3": ("BitstampExchange", BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))),
    "4": ("KucoinExchange", KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))),
    #"5": ("CoinbaseExchange", CoinbaseExchange(api_key=os.getenv("COINBASE_API_KEY"), secret=os.getenv("COINBASE_SECRET")))
}

def get_exchange_instance_by_name(name: str):
    """Zwraca instancję giełdy na podstawie nazwy."""
    for key, (ex_name, instance) in EXCHANGE_OPTIONS.items():
        if ex_name == name:
            return instance
    return None

async def create_all_common_pairs():
    """
    Automatycznie pobiera wspólne pary dla każdej kombinacji dwóch giełd
    i zapisuje wyniki do pliku 'common_pairs_all.json'.
    
    Struktura zapisywanych danych:
      {
         "ExchangeA-ExchangeB": [ (symbolA, symbolB, normalized_symbol), ... ],
         "ExchangeA-ExchangeC": [ ... ],
         ...
      }
    """
    common_pairs_all = {}
    async with aiohttp.ClientSession() as session:
        # Iterujemy po wszystkich kombinacjach dwóch giełd
        for ((key1, (name1, exch1)), (key2, (name2, exch2))) in itertools.combinations(EXCHANGE_OPTIONS.items(), 2):
            logging.info(f"Przetwarzanie konfiguracji: {name1} - {name2}")
            # Pobieramy listy par z obu giełd
            pairs1 = await exch1.get_trading_pairs(session)
            pairs2 = await exch2.get_trading_pairs(session)
            mapping1 = {normalize_symbol(sym, name1): sym for sym in pairs1}
            mapping2 = {normalize_symbol(sym, name2): sym for sym in pairs2}
            common_norm = set(mapping1.keys()) & set(mapping2.keys())
            common_list = [(mapping1[norm], mapping2[norm], norm) for norm in common_norm]
            pair_key = f"{name1}-{name2}"
            common_pairs_all[pair_key] = common_list
    filename = "common_pairs_all.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(common_pairs_all, f, ensure_ascii=False, indent=4)
    print(f"Wszystkie wspólne pary zapisane w {filename}")

async def simulate_arbitrage_from_common():
    """
    Symulacja arbitrażu przy użyciu wcześniej utworzonej listy wspólnych par
    (plik 'common_pairs_all.json'). Użytkownik wybiera giełdę, na której posiada środki,
    deklaruje kwotę oraz minimalny oczekiwany zysk. Program przeszukuje wszystkie konfiguracje,
    w których występuje wybrana giełda jako źródło, i sprawdza potencjalne okazje arbitrażowe.
    
    Jeśli znajdzie opłacalną okazję (zysk >= zadeklarowany próg), symuluje transakcję:
      - Kupno na giełdzie źródłowej,
      - „Transfer” na giełdę docelową,
      - Sprzedaż na giełdzie docelowej.
    
    Po udanej transakcji środki zostają zaktualizowane, a giełda źródłowa zmienia się na docelową,
    po czym proces jest powtarzany.
    """
    filename = "common_pairs_all.json"
    if not os.path.exists(filename):
        print("Plik common_pairs_all.json nie istnieje. Najpierw utwórz listę wspólnych par (opcja 1).")
        return

    with open(filename, "r", encoding="utf-8") as f:
        common_pairs_all = json.load(f)

    # Wybór giełdy źródłowej (gdzie posiadamy środki)
    print("Wybierz giełdę, na której masz dostępne środki:")
    for key, (name, _) in EXCHANGE_OPTIONS.items():
        print(f"{key}: {name}")
    source_choice = input("Wybierz giełdę (numer): ").strip()
    if source_choice not in EXCHANGE_OPTIONS:
        print("Nieprawidłowy wybór.")
        return
    source_name, source_instance = EXCHANGE_OPTIONS[source_choice]

    try:
        funds = float(input("Podaj kwotę środków dostępnych na giełdzie (np. 1000): ").strip())
    except ValueError:
        print("Nieprawidłowa kwota.")
        return

    try:
        min_profit = float(input("Podaj minimalny zysk (w walucie) z pojedynczego arbitrażu (np. 10): ").strip())
    except ValueError:
        print("Nieprawidłowa wartość minimalnego zysku – ustawiam 10.")
        min_profit = 10.0

    current_exchange_name = source_name
    current_instance = source_instance

    print(f"\nRozpoczynam symulację arbitrażu z giełdy {current_exchange_name} z kwotą {funds:.2f}.\n")

    async with aiohttp.ClientSession() as session:
        while True:
            opportunities = []
            # Przeglądamy wszystkie konfiguracje, w których występuje bieżąca giełda
            for config_key, pairs in common_pairs_all.items():
                # Konfiguracja w formacie "ExchangeA-ExchangeB"
                if current_exchange_name not in config_key:
                    continue
                parts = config_key.split("-")
                if parts[0] == current_exchange_name:
                    # W tej konfiguracji giełda źródłowa jest pierwsza, docelowa to parts[1]
                    dest_name = parts[1]
                    for tup in pairs:
                        # Tupel jest zapisany jako (symbol z giełdy A, symbol z giełdy B, normalized)
                        source_sym = tup[0]
                        dest_sym = tup[1]
                        normalized = tup[2]
                        price_source = await current_instance.get_price(source_sym, session)
                        dest_instance = get_exchange_instance_by_name(dest_name)
                        price_dest = await dest_instance.get_price(dest_sym, session)
                        if price_source is None or price_dest is None:
                            continue
                        if price_source < price_dest:
                            profit = funds * ((price_dest / price_source) - 1)
                            if profit >= min_profit:
                                opportunities.append({
                                    "asset": normalized,
                                    "buy_exchange": current_exchange_name,
                                    "sell_exchange": dest_name,
                                    "price_buy": price_source,
                                    "price_sell": price_dest,
                                    "profit": profit,
                                })
                elif parts[1] == current_exchange_name:
                    # W tej konfiguracji bieżąca giełda jest druga, więc w tupelu:
                    # symbol dla bieżącej giełdy to tup[1], a dla docelowej to tup[0]
                    dest_name = parts[0]
                    for tup in pairs:
                        source_sym = tup[1]
                        dest_sym = tup[0]
                        normalized = tup[2]
                        price_source = await current_instance.get_price(source_sym, session)
                        dest_instance = get_exchange_instance_by_name(dest_name)
                        price_dest = await dest_instance.get_price(dest_sym, session)
                        if price_source is None or price_dest is None:
                            continue
                        if price_source < price_dest:
                            profit = funds * ((price_dest / price_source) - 1)
                            if profit >= min_profit:
                                opportunities.append({
                                    "asset": normalized,
                                    "buy_exchange": current_exchange_name,
                                    "sell_exchange": dest_name,
                                    "price_buy": price_source,
                                    "price_sell": price_dest,
                                    "profit": profit,
                                })
            if opportunities:
                best = max(opportunities, key=lambda x: x["profit"])
                print("\nZnaleziono okazję arbitrażową:")
                print(f"  Asset: {best['asset']}")
                print(f"  Kup na {best['buy_exchange']} po {best['price_buy']}")
                print(f"  Sprzedaj na {best['sell_exchange']} po {best['price_sell']}")
                print(f"  Szacowany zysk: {best['profit']:.2f}")
                # Symulacja transakcji – przyjmujemy, że cała kwota jest wykorzystana
                funds = funds * (best["price_sell"] / best["price_buy"])
                print(f"Transakcja przeprowadzona. Nowa kwota środków: {funds:.2f}")
                # Aktualizujemy bieżącą giełdę – środki trafiają na giełdę docelową
                current_exchange_name = best["sell_exchange"]
                current_instance = get_exchange_instance_by_name(current_exchange_name)
            else:
                print("Brak opłacalnych okazji arbitrażowych w tej rundzie.")
            print("-" * 60)
            await asyncio.sleep(10)

async def main():
    while True:
        print("\nWybierz opcję:")
        print("1. Utwórz/odśwież listę wspólnych par dla wszystkich giełd")
        print("2. Uruchom symulację arbitrażu (wykorzystując wcześniej utworzoną listę)")
        print("3. Wyjście")
        choice = input("Twój wybór: ").strip()
        if choice == "1":
            await create_all_common_pairs()
        elif choice == "2":
            await simulate_arbitrage_from_common()
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
