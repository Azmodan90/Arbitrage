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
import logger_config

# Konfiguracja logowania z centralnego modułu
logger_config.setup_logging()

def setup_signal_handlers(loop):
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name, loop)))

async def shutdown(signal_name, loop):
    logging.info(f"\nOtrzymano sygnał {signal_name}. Zatrzymywanie programu...")
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
    logging.info("Anulowanie zadań: %s", tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0.2)
    await loop.shutdown_asyncgens()

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
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logging.info("Arbitraż został przerwany.")
    else:
        logging.info("Brak aktywnych zadań arbitrażu do uruchomienia.")

async def main():
    logging.info("Uruchamianie programu arbitrażowego")
    
    exchanges = {
        "binance": BinanceExchange(),
        "kucoin": KucoinExchange(),
        "bitget": BitgetExchange(),
        "bitstamp": BitstampExchange()
    }
    
    loop = asyncio.get_running_loop()
    setup_signal_handlers(loop)
    
    try:
        while True:
            print("\nWybierz opcję:")
            print("1. Utwórz listę wspólnych aktywów")
            print("2. Rozpocznij arbitraż (dla aktywów z common_assets.json)")
            print("3. Wyjście")
            choice = input("Twój wybór (1/2/3): ").strip()
            if choice == "1":
                logging.info("Wybrano opcję tworzenia listy wspólnych aktywów")
                await common_assets.main()
            elif choice == "2":
                logging.info("Wybrano opcję rozpoczęcia arbitrażu")
                await run_arbitrage_for_all_pairs(exchanges)
            elif choice == "3":
                logging.info("Wyjście z programu")
                break
            else:
                logging.error("Nieprawidłowy wybór!")
                print("Nieprawidłowy wybór!")
    except (KeyboardInterrupt, asyncio.CancelledError):
        logging.info("Program zatrzymany przez użytkownika.")
    finally:
        await exchanges["binance"].close()
        await exchanges["kucoin"].close()
        await exchanges["bitget"].close()
        await exchanges["bitstamp"].close()

if __name__ == '__main__':
    asyncio.run(main())
