import asyncio
import signal
import logging
import json
from config import CONFIG
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from arbitrage import PairArbitrageStrategy
import common_assets

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    if logger.hasHandlers():
        logger.handlers.clear()
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    file_handler = logging.FileHandler('app.log', mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

async def shutdown(signal_name, loop):
    logging.info(f"\nOtrzymano sygnał {signal_name}. Zatrzymywanie programu...")
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
    logging.info("Anulowanie zadań: %s", tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0.2)

def setup_signal_handlers(loop):
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name, loop)))

async def run_arbitrage_for_all_pairs(exchanges):
    try:
        with open("common_assets.json", "r") as f:
            common_assets_data = json.load(f)
    except Exception as e:
        logging.error(f"Nie udało się załadować common_assets.json: {e}")
        return

    tasks = []
    for pair_key, assets in common_assets_data.items():
        if not assets:
            logging.info(f"Brak wspólnych aktywów dla pary {pair_key}")
            continue
        exch_names = pair_key.split("-")
        if len(exch_names) != 2:
            logging.error(f"Niepoprawny format pary: {pair_key}")
            continue
        ex1 = exchanges.get(exch_names[0])
        ex2 = exchanges.get(exch_names[1])
        if not ex1 or not ex2:
            logging.error(f"Nie znaleziono giełd dla pary: {pair_key}")
            continue
        strategy = PairArbitrageStrategy(ex1, ex2, assets, pair_name=pair_key)
        tasks.append(asyncio.create_task(strategy.run()))
    if tasks:
        await asyncio.gather(*tasks)
    else:
        logging.info("Brak aktywnych zadań arbitrażu do uruchomienia.")

def run_arbitrage(exchanges):
    logging.info("Wybrano opcję rozpoczęcia arbitrażu")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    setup_signal_handlers(loop)
    try:
        loop.run_until_complete(run_arbitrage_for_all_pairs(exchanges))
    except asyncio.CancelledError:
        logging.info("Zadania anulowane")
    except KeyboardInterrupt:
        logging.info("Program zatrzymany przez użytkownika (CTRL+C)")
    finally:
        pending = asyncio.all_tasks(loop)
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.close()

def main():
    setup_logging()
    logging.info("Uruchamianie programu arbitrażowego")
    
    exchanges = {
        "binance": BinanceExchange(),
        "kucoin": KucoinExchange(),
        "bitget": BitgetExchange(),
        "bitstamp": BitstampExchange()
    }
    
    while True:
        print("\nWybierz opcję:")
        print("1. Utwórz listę wspólnych aktywów")
        print("2. Rozpocznij arbitraż (dla aktywów z common_assets.json)")
        print("3. Wyjście")
        choice = input("Twój wybór (1/2/3): ").strip()
        if choice == "1":
            logging.info("Wybrano opcję tworzenia listy wspólnych aktywów")
            common_assets.main()
        elif choice == "2":
            run_arbitrage(exchanges)
        elif choice == "3":
            logging.info("Wyjście z programu")
            break
        else:
            logging.error("Nieprawidłowy wybór!")
            print("Nieprawidłowy wybór!")

if __name__ == '__main__':
    main()
