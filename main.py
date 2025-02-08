import sys
import asyncio
import logging
import os
from common_pairs import create_common_pairs
from arbitrage import run_arbitrage

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
    print("1 - Utwórz listę wspólnych aktywów")
    print("2 - Uruchom arbitraż")
    print("3 - Wyjście")

def main():
    while True:
        print_menu()
        choice = input("Podaj numer opcji: ").strip()
        if choice == "1":
            asyncio.run(create_common_pairs())
        elif choice == "2":
            asyncio.run(run_arbitrage())
        elif choice == "3":
            print("Wyjście.")
            sys.exit(0)
        else:
            print("Nieprawidłowy wybór.")

if __name__ == "__main__":
    main()
