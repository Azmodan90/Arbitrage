# main.py

import os
import asyncio
import aiohttp
import logging
from dotenv import load_dotenv
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange

load_dotenv()
logging.basicConfig(level=logging.INFO)

async def get_common_pairs(exchange1, exchange2, session: aiohttp.ClientSession):
    pairs1 = await exchange1.get_trading_pairs(session)
    pairs2 = await exchange2.get_trading_pairs(session)
    common = set(pairs1) & set(pairs2)
    return list(common)

async def main():
    async with aiohttp.ClientSession() as session:
        # Tworzymy instancje giełd – pobieramy klucze API z .env, jeśli są wymagane
        binance = BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))
        kucoin = KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))
        bitget = BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))
        bitstamp = BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))
        
        # Przykład: wyznaczamy wspólne pary między Bitget a Bitstamp
        common_pairs = await get_common_pairs(bitget, bitstamp, session)
        logging.info(f"Wspólne pary między Bitget a Bitstamp: {common_pairs}")

        # Dla każdej wspólnej pary pobieramy ceny i porównujemy je
        arbitrage_opportunities = []
        for pair in common_pairs:
            price_bitget = await bitget.get_price(pair, session)
            price_bitstamp = await bitstamp.get_price(pair, session)
            if price_bitget is None or price_bitstamp is None:
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
        
        logging.info("Znalezione okazje arbitrażowe:")
        for opp in arbitrage_opportunities:
            logging.info(opp)

if __name__ == "__main__":
    asyncio.run(main())
