import asyncio
import signal
import logging
from config import CONFIG
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from arbitrage import PairArbitrageStrategy
import common_assets

logger = logging.getLogger("app")

async def shutdown(signal_name, loop, tasks, exchanges):
    logger.info(f"Received signal {signal_name}. Cancelling tasks...")
    for task in tasks:
        task.cancel()
    # Czekamy na anulowanie zadań
    await asyncio.gather(*tasks, return_exceptions=True)
    logger.info("Tasks cancelled. Closing exchange connections...")
    # Zamykamy wszystkie exchange (jeśli mają metodę close)
    for ex in exchanges.values():
        await ex.close()
    logger.info("Shutdown complete.")
    loop.stop()

async def run_arbitrage_for_all_pairs(exchanges):
    try:
        with open("common_assets.json", "r") as f:
            common_assets_data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load common_assets.json: {e}")
        return

    tasks = []
    for pair_key, assets in common_assets_data.items():
        if not assets:
            logger.info(f"No common assets for pair {pair_key}")
            continue
        exch_names = pair_key.split("-")
        if len(exch_names) != 2:
            logger.error(f"Invalid pair format: {pair_key}")
            continue
        ex1 = exchanges.get(exch_names[0])
        ex2 = exchanges.get(exch_names[1])
        if not ex1 or not ex2:
            logger.error(f"Exchanges not found for pair: {pair_key}")
            continue
        strategy = PairArbitrageStrategy(ex1, ex2, assets, pair_name=pair_key)
        tasks.append(asyncio.create_task(strategy.run()))
    if tasks:
        await asyncio.gather(*tasks)
    else:
        logger.info("No arbitrage tasks to run.")

async def main():
    # Inicjalizacja loggera, giełd itp.
    logger.info("Starting arbitrage program")
    exchanges = {
        "binance": BinanceExchange(),
        "kucoin": KucoinExchange(),
        "bitget": BitgetExchange(),
        "bitstamp": BitstampExchange()
    }
    
    # Tworzymy zadanie główne
    main_task = asyncio.create_task(run_arbitrage_for_all_pairs(exchanges))
    
    loop = asyncio.get_running_loop()
    # Ustawiamy signal handler’y
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name, loop, [main_task], exchanges)))
    
    try:
        await main_task
    except asyncio.CancelledError:
        logger.info("Main task cancelled.")

if __name__ == '__main__':
    asyncio.run(main())
