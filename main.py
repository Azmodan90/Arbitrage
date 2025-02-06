# main.py

import os
import asyncio
import aiohttp
import logging
from dotenv import load_dotenv
# Importy innych giełd – zakładamy, że masz już implementacje dla Binance i Kucoin
from exchanges.binance import BinanceExchange  
from exchanges.kucoin import KucoinExchange    
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange

# Konfiguracja logowania: logi wyświetlane w konsoli oraz zapisywane w pliku app.log
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("app.log", encoding="utf-8")
    ]
)

# Wczytujemy zmienne środowiskowe z pliku .env
load_dotenv()
logging.info("Program uruchomiony.")

async def get_common_pairs(exchange1, exchange2, session: aiohttp.ClientSession):
    logging.info(f"Pobieranie par z {exchange1.__class__.__name__} i {exchange2.__class__.__name__}")
    pairs1 = await exchange1.get_trading_pairs(session)
    pairs2 = await exchange2.get_trading_pairs(session)
    common = set(pairs1) & set(pairs2)
    logging.info(f"Wspólne pary: {list(common)}")
    return list(common)

async def main():
    async with aiohttp.ClientSession() as session:
        # Inicjalizacja giełd – klucze API pobieramy z .env (upewnij się, że masz je zdefiniowane)
        binance = BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))
        kucoin = KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))
        bitget = BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))
        bitstamp = BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))
        
        # Przykład: pobieranie wspólnych par między Bitget a Bitstamp
        common_pairs = await get_common_pairs(bitget, bitstamp, session)
        if not common_pairs:
            logging.warning("Brak wspólnych par między Bitget a Bitstamp.")
        else:
            logging.info(f"Znaleziono wspólne pary: {common_pairs}")

        arbitrage_opportunities = []
        for pair in common_pairs:
            price_bitget = await bitget.get_price(pair, session)
            price_bitstamp = await bitstamp.get_price(pair, session)
            logging.info(f"Ceny dla {pair}: Bitget = {price_bitget}, Bitstamp = {price_bitstamp}")
            if price_bitget is None or price_bitstamp is None:
                logging.error(f"Nie udało się pobrać ceny dla {pair}")
                continue

            if price_bitget < price_bitstamp:
                diff = ((price_bitstamp - price_bitget) / price_bitget) * 100
                arbitrage_opportunities.append({
                    "pair": pair,
                    "buy": "Bitget",
                    "sell": "Bitstamp",
                    "price_buy": price_bitget,
                    "price_sell": price_bitstamp,
                    "difference_percent": diff
                })
                logging.info(f"Okazja arbitrażowa: Kup na Bitget po {price_bitget}, sprzedaj na Bitstamp po {price_bitstamp} - różnica: {diff:.2f}%")
            elif price_bitstamp < price_bitget:
                diff = ((price_bitget - price_bitstamp) / price_bitstamp) * 100
                arbitrage_opportunities.append({
                    "pair": pair,
                    "buy": "Bitstamp",
                    "sell": "Bitget",
                    "price_buy": price_bitstamp,
                    "price_sell": price_bitget,
                    "difference_percent": diff
                })
                logging.info(f"Okazja arbitrażowa: Kup na Bitstamp po {price_bitstamp}, sprzedaj na Bitget po {price_bitget} - różnica: {diff:.2f}%")

        if arbitrage_opportunities:
            logging.info("Znalezione okazje arbitrażowe:")
            for opp in arbitrage_opportunities:
                logging.info(opp)
        else:
            logging.info("Brak okazji arbitrażowych.")

if __name__ == "__main__":
    asyncio.run(main())
