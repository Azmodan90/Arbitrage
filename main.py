import os
import asyncio
import aiohttp
import logging
import json
import itertools
from dotenv import load_dotenv
from create_common_pairs import create_all_common_pairs  # Import funkcji do tworzenia wspólnych par
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange
# from exchanges.coinbase import CoinbaseExchange  # opcjonalnie
from utils import normalize_symbol

# Konfiguracja logowania – logi trafiają do konsoli oraz do pliku "app.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

load_dotenv()

# Mapowanie dostępnych giełd: klucz -> (nazwa, instancja)
EXCHANGE_OPTIONS = {
    "1": ("BinanceExchange", BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))),
    "2": ("BitgetExchange", BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))),
    "3": ("BitstampExchange", BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))),
    "4": ("KucoinExchange", KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET")))
    # "5": ("CoinbaseExchange", CoinbaseExchange(api_key=os.getenv("COINBASE_API_KEY"), secret=os.getenv("COINBASE_SECRET")))
}

def get_exchange_instance_by_name(name: str):
    """Zwraca instancję giełdy na podstawie nazwy."""
    for key, (ex_name, instance) in EXCHANGE_OPTIONS.items():
        if ex_name == name:
            return instance
    return None

# Pomocnicza funkcja, która równolegle pobiera ceny dla jednej pary
async def fetch_price_task(buy_exchange: str, sell_exchange: str, normalized: str,
                             source_sym: str, dest_sym: str,
                             current_instance, dest_instance, session: aiohttp.ClientSession):
    price_source = await current_instance.get_price(source_sym, session)
    price_dest = await dest_instance.get_price(dest_sym, session)
    return (normalized, price_source, price_dest, buy_exchange, sell_exchange)

async def simulate_arbitrage_from_common():
    """
    Symulacja arbitrażu przy użyciu listy wspólnych par zapisanej w pliku 'common_pairs_all.json'.
    Użytkownik wybiera giełdę źródłową (gdzie posiada środki), podaje dostępne środki oraz minimalny zysk.
    Następnie program przeszukuje konfiguracje i (symuluje) transakcje, aktualizując stan środków.
    Zamiast pobierać ceny sekwencyjnie, dla każdej konfiguracji tworzona jest lista zadań, które są
    uruchamiane równolegle.
    """
    filename = "common_pairs_all.json"
    if not os.path.exists(filename):
        print("Plik common_pairs_all.json nie istnieje. Najpierw utwórz listę wspólnych par (opcja 1).")
        return

    with open(filename, "r", encoding="utf-8") as f:
        common_pairs_all = json.load(f)

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
            tasks = []
            # Przeglądamy wszystkie konfiguracje, w których występuje bieżąca giełda
            for config_key, pairs in common_pairs_all.items():
                if current_exchange_name not in config_key:
                    continue
                parts = config_key.split("-")
                if parts[0] == current_exchange_name:
                    # Obecna giełda jako pierwsza – docelowa to parts[1]
                    dest_name = parts[1]
                    dest_instance = get_exchange_instance_by_name(dest_name)
                    for tup in pairs:
                        source_sym = tup[0]  # już znormalizowany symbol dla bieżącej giełdy
                        dest_sym = tup[1]    # już znormalizowany symbol dla docelowej giełdy
                        normalized = tup[2]
                        tasks.append(fetch_price_task(current_exchange_name, dest_name, normalized,
                                                       source_sym, dest_sym,
                                                       current_instance, dest_instance, session))
                elif parts[1] == current_exchange_name:
                    # Obecna giełda jako druga – docelowa to parts[0]
                    dest_name = parts[0]
                    dest_instance = get_exchange_instance_by_name(dest_name)
                    for tup in pairs:
                        source_sym = tup[1]  # dla bieżącej giełdy (drugiej) używamy drugiego symbolu
                        dest_sym = tup[0]
                        normalized = tup[2]
                        tasks.append(fetch_price_task(current_exchange_name, dest_name, normalized,
                                                       source_sym, dest_sym,
                                                       current_instance, dest_instance, session))
            # Uruchamiamy wszystkie zadania równolegle
            results = await asyncio.gather(*tasks, return_exceptions=True)
            opportunities = []
            for result in results:
                if isinstance(result, Exception):
                    continue
                normalized, price_source, price_dest, buy_exchange, sell_exchange = result
                if price_source is None or price_dest is None or price_source == 0 or price_dest == 0:
                    continue
                if price_source < price_dest:
                    profit = funds * ((price_dest / price_source) - 1)
                    if profit >= min_profit:
                        opportunities.append({
                            "asset": normalized,
                            "buy_exchange": buy_exchange,
                            "sell_exchange": sell_exchange,
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
                # Zakładamy wykorzystanie całej kwoty
                funds = funds * (best["price_sell"] / best["price_buy"])
                print(f"Transakcja przeprowadzona. Nowa kwota środków: {funds:.2f}")
                # Aktualizacja – środki przechodzą na giełdę docelową
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
    except KeyboardInterrupt:
        logging.info("Program zakończony przez użytkownika (Ctrl+C).")
