import sys
import asyncio
import logging
import os
from create_common_pairs import create_all_common_pairs
from arbitrage_strategy import find_arbitrage_opportunities

# Konfiguracja logowania – logi zapisywane są w folderze "log"
LOG_DIR = "log"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(LOG_DIR, "app.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)

def print_menu():
    print("Wybierz opcję:")
    print("1 - Utwórz listę wspólnych aktywów dla par giełd")
    print("2 - Porównaj ceny i szukaj okazji arbitrażu")
    print("3 - Wyjście")

def main():
    while True:
        print_menu()
        choice = input("Podaj numer opcji: ").strip()
        if choice == "1":
            # Opcja 1: Utworzenie listy wspólnych aktywów
            asyncio.run(create_all_common_pairs())
        elif choice == "2":
            # Opcja 2: Porównanie cen i wyszukanie okazji arbitrażu
            asyncio.run(find_arbitrage_opportunities())
        elif choice == "3":
            print("Wyjście z programu.")
            sys.exit(0)
        else:
            print("Nieprawidłowy wybór. Spróbuj ponownie.")

if __name__ == "__main__":
    main()
