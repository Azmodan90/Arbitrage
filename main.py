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
    file_handler = logging.FileHandler('app.log', mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

async def shutdown(signal_name, loop):
    logging.info(f"\nReceived signal {signal_name}. Shutting down...")
    tasks = [t for t in asyncio.all_tasks(loop) if t is not asyncio.current_task(loop)]
    logging.info("Cancelling tasks: %s", tasks)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0.1)
    await loop.shutdown_asyncgens()

def setup_signal_handlers(loop):
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name, loop)))

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
        await asyncio.gather(*tasks, return_exceptions=True)
    else:
        logging.info("No arbitrage tasks to run.")

async def main():
    setup_logging()
    logging.info("Starting arbitrage program")
    
    exchanges = {
        "binance": BinanceExchange(),
        "kucoin": KucoinExchange(),
        "bitget": BitgetExchange(),
        "bitstamp": BitstampExchange()
    }
    
    while True:
        print("\nChoose an option:")
        print("1. Create common assets list")
        print("2. Start arbitrage (using assets from common_assets.json)")
        print("3. Exit")
        choice = input("Your choice (1/2/3): ").strip()
        if choice == "1":
            await common_assets.main()  # common_assets.main() is async
        elif choice == "2":
            await run_arbitrage_for_all_pairs(exchanges)
        elif choice == "3":
            logging.info("Exiting program")
            break
        else:
            logging.error("Invalid choice!")
            print("Invalid choice!")
    
    await exchanges["binance"].close()
    await exchanges["kucoin"].close()
    await exchanges["bitget"].close()
    await exchanges["bitstamp"].close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Program terminated by user")
