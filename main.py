import asyncio
import signal
import logging
from config import CONFIG
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from arbitrage import ArbitrageStrategy
import common_assets

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    
    # Czyścimy istniejące handlery, by uniknąć duplikacji
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Handler do terminala
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler do pliku
    file_handler = logging.FileHandler('app.log', mode='a', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

async def shutdown(signal_name, loop):
    logging.info(f"\nOtrzymano sygnał {signal_name}. Zatrzymywanie programu...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    [task.cancel() for task in tasks]
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def setup_signal_handlers(loop):
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s.name, loop)))

def run_arbitrage(exchanges):
    logging.info("Wybrano opcję rozpoczęcia arbitrażu")
    arbitrage = ArbitrageStrategy(exchanges)
    # Tworzymy nowy event loop, aby po zakończeniu móc wrócić do menu
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    setup_signal_handlers(loop)
    try:
        loop.run_until_complete(arbitrage.run("BTC/USDT"))
    except asyncio.CancelledError:
        logging.info("Zadania anulowane")
    except KeyboardInterrupt:
        logging.info("Program zatrzymany przez użytkownika (CTRL+C)")
    finally:
        loop.close()

def main():
    setup_logging()
    logging.info("Uruchamianie programu arbitrażowego")
    
    # Inicjalizacja instancji giełd
    exchanges = {
        "binance": BinanceExchange(),
        "kucoin": KucoinExchange(),
        "bitget": BitgetExchange(),
        "bitstamp": BitstampExchange()
    }
    
    while True:
        print("\nWybierz opcję:")
        print("1. Utwórz listę wspólnych aktywów")
        print("2. Rozpocznij arbitraż")
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
