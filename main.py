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
    # Usuwamy istniejące handlery, żeby nie dublować logów
    if logger.hasHandlers():
        logger.handlers.clear()
    file_handler = logging.FileHandler('app.log', mode='a', encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

async def shutdown(loop):
    logging.info("Shutdown initiated, cancelling tasks...")
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
    if tasks:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    logging.info("All tasks cancelled. Shutting down loop.")
    loop.stop()

def install_signal_handlers(loop):
    # Rejestrujemy sygnały do wywołania shutdown
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(shutdown(loop)))

async def run_arbitrage_for_all_pairs(exchanges):
    try:
        with open("common_assets.json", "r") as f:
            common_assets_data = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load common_assets.json: {e}")
        return

    tasks = []
    for pair_key, assets in common_assets_data.items():
        if not assets:
            logging.info(f"No common assets for pair {pair_key}")
            continue
        exch_names = pair_key.split("-")
        if len(exch_names) != 2:
            logging.error(f"Invalid pair format: {pair_key}")
            continue
        ex1 = exchanges.get(exch_names[0])
        ex2 = exchanges.get(exch_names[1])
        if not ex1 or not ex2:
            logging.error(f"Exchanges not found for pair: {pair_key}")
            continue
        strategy = PairArbitrageStrategy(ex1, ex2, assets, pair_name=pair_key)
        tasks.append(asyncio.create_task(strategy.run()))
    if tasks:
        await asyncio.gather(*tasks)
    else:
        logging.info("No arbitrage tasks to run.")

async def main():
    setup_logging()
    logging.info("Starting arbitrage program")

    # Inicjalizacja giełd
    exchanges = {
        "binance": BinanceExchange(),
        "kucoin": KucoinExchange(),
        "bitget": BitgetExchange(),
        "bitstamp": BitstampExchange()
    }

    loop = asyncio.get_running_loop()
    install_signal_handlers(loop)

    while True:
        print("\nChoose an option:")
        print("1. Create common assets list")
        print("2. Start arbitrage (using assets from common_assets.json)")
        print("3. Exit")
        choice = input("Your choice (1/2/3): ").strip()
        if choice == "1":
            await common_assets.main()
        elif choice == "2":
            await run_arbitrage_for_all_pairs(exchanges)
        elif choice == "3":
            logging.info("Exiting program")
            break
        else:
            logging.error("Invalid choice!")
            print("Invalid choice!")

    # Zamykamy instancje giełd
    await exchanges["binance"].close()
    await exchanges["kucoin"].close()
    await exchanges["bitget"].close()
    await exchanges["bitstamp"].close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Jeśli z jakiegoś powodu pozostały niewyłapane KeyboardInterrupty, wychodzimy
        logging.info("Program interrupted by user (KeyboardInterrupt).")
