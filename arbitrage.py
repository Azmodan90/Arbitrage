import os
import asyncio
import aiohttp
import json
import logging
from dotenv import load_dotenv
from exchanges.binance import BinanceExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange
from exchanges.kucoin import KucoinExchange

load_dotenv()

# Konfiguracja logowania – logi zapisywane są w pliku "app.log" w głównym folderze
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)

EXCHANGE_INSTANCES = {
    "BinanceExchange": BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET")),
    "BitgetExchange": BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET")),
    "BitstampExchange": BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET")),
    "KucoinExchange": KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))
}

FEES = {
    "BinanceExchange": 0.001,
    "BitgetExchange": 0.002,
    "BitstampExchange": 0.005,
    "KucoinExchange": 0.001
}

async def fetch_price(exchange, symbol, session):
    try:
        return await exchange.get_price(symbol, session)
    except Exception as e:
        logging.error(f"Błąd pobierania ceny {symbol} z {exchange.__class__.__name__}: {e}")
        return 0.0

async def run_arbitrage():
    if not os.path.exists("common_pairs.json"):
        logging.error("Plik common_pairs.json nie istnieje. Uruchom najpierw common_pairs.py")
        return

    with open("common_pairs.json", "r", encoding="utf-8") as f:
        common_pairs = json.load(f)

    async with aiohttp.ClientSession() as session:
        for key, symbols in common_pairs.items():
            exchanges = key.split("-")
            if len(exchanges) != 2:
                continue
            ex1_name, ex2_name = exchanges
            ex1 = EXCHANGE_INSTANCES.get(ex1_name)
            ex2 = EXCHANGE_INSTANCES.get(ex2_name)
            fee1 = FEES.get(ex1_name, 0)
            fee2 = FEES.get(ex2_name, 0)
            if not ex1 or not ex2:
                continue

            for symbol in symbols:
                price1 = await fetch_price(ex1, symbol, session)
                price2 = await fetch_price(ex2, symbol, session)
                if price1 == 0 or price2 == 0:
                    continue

                effective_price1 = price1 * (1 + fee1)
                effective_price2 = price2 * (1 - fee2)

                if effective_price1 < price2:
                    profit = ((price2 - effective_price1) / effective_price1) * 100
                    logging.info(f"Arbitraż: Kup {symbol} na {ex1_name} za {price1:.4f} (efektywnie {effective_price1:.4f}) "
                                 f"i sprzedaj na {ex2_name} za {price2:.4f}. Zysk: {profit:.2f}%")
                elif effective_price2 < price1:
                    profit = ((price1 - effective_price2) / effective_price2) * 100
                    logging.info(f"Arbitraż: Kup {symbol} na {ex2_name} za {price2:.4f} (efektywnie {effective_price2:.4f}) "
                                 f"i sprzedaj na {ex1_name} za {price1:.4f}. Zysk: {profit:.2f}%")

if __name__ == "__main__":
    asyncio.run(run_arbitrage())
