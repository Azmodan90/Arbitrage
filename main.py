import os
import asyncio
import logging
import json
import itertools
from dotenv import load_dotenv
from common_assets import create_all_common_pairs  # Zmiana importu na common_assets.py
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange
from utils import normalize_symbol

load_dotenv()

# Konfiguracja logowania
logger = logging.getLogger()
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
all_handler = logging.FileHandler("app.log", encoding="utf-8")
all_handler.setLevel(logging.INFO)
error_handler = logging.FileHandler("error.log", encoding="utf-8")
error_handler.setLevel(logging.ERROR)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
all_handler.setFormatter(formatter)
error_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logger.addHandler(all_handler)
logger.addHandler(error_handler)

# Mapowanie dostępnych giełd: klucz -> (nazwa, instancja)
EXCHANGE_OPTIONS = {
    "1": ("BinanceExchange", BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))),
    "2": ("BitgetExchange", BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))),
    "3": ("BitstampExchange", BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))),
    "4": ("KucoinExchange", KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET")))
}

def get_exchange_instance_by_name(name: str):
    for key, (ex_name, instance) in EXCHANGE_OPTIONS.items():
        if ex_name == name:
            return instance
    return None

async def fetch_opportunity(tup, current_instance, dest_instance, funds, min_profit, source_name, dest_name):
    source_sym, dest_sym, normalized = tup
    price_source, price_dest = await asyncio.gather(
        current_instance.get_price(source_sym),
        dest_instance.get_price(dest_sym)
    )
    if price_source is None or price_dest is None or price_source == 0 or price_dest == 0:
        return None
    if price_source < price_dest:
        profit = funds * ((price_dest / price_source) - 1)
        if profit >= min_profit:
            return {
                "asset": normalized,
                "buy_exchange": source_name,
                "sell_exchange": dest_name,
                "price_buy": price_source,
                "price_sell": price_dest,
                "profit": profit
            }
    return None

async def simulate_arbitrage_from_common():
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
    try:
        while True:
            opportunities = []
            for config_key, pairs in common_pairs_all.items():
                if current_exchange_name not in config_key:
                    continue
                parts = config_key.split("-")
                if parts[0] == current_exchange_name:
                    dest_name = parts[1]
                    dest_instance = get_exchange_instance_by_name(dest_name)
                    tasks = [asyncio.create_task(
                        fetch_opportunity(tup, current_instance, dest_instance, funds, min_profit, current_exchange_name, dest_name)
                    ) for tup in pairs]
                    results = await asyncio.gather(*tasks)
                    for res in results:
                        if res is not None:
                            opportunities.append(res)
                elif parts[1] == current_exchange_name:
                    dest_name = parts[0]
                    dest_instance = get_exchange_instance_by_name(dest_name)
                    tasks = [asyncio.create_task(
                        fetch_opportunity((tup[1], tup[0], tup[2]), current_instance, dest_instance, funds, min_profit, current_exchange_name, dest_name)
                    ) for tup in pairs]
                    results = await asyncio.gather(*tasks)
                    for res in results:
                        if res is not None:
                            opportunities.append(res)
            if opportunities:
                best = max(opportunities, key=lambda x: x["profit"])
                print("\nZnaleziono okazję arbitrażową:")
                print(f" Asset: {best['asset']}")
                print(f" Kup na {best['buy_exchange']} po {best['price_buy']}")
                print(f" Sprzedaj na {best['sell_exchange']} po {best['price_sell']}")
                print(f" Szacowany zysk: {best['profit']:.2f}")
                funds = funds * (best["price_sell"] / best["price_buy"])
                print(f"Transakcja przeprowadzona. Nowa kwota środków: {funds:.2f}")
                current_exchange_name = best["sell_exchange"]
                current_instance = get_exchange_instance_by_name(current_exchange_name)
            else:
                print("Brak opłacalnych okazji arbitrażowych w tej rundzie.")
            print("-" * 60)
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        print("Symulacja arbitrażu została anulowana.")

async def main():
    try:
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
    finally:
        # Zamykamy wszystkie instancje giełdowe, aby zwolnić zasoby
        for key, (name, instance) in EXCHANGE_OPTIONS.items():
            try:
                await instance.close()
            except Exception as e:
                logging.error(f"Błąd przy zamykaniu giełdy {name}: {e}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Program zakończony przez użytkownika (Ctrl+C).")
