# main.py

import os
import asyncio
import aiohttp
import logging
from dotenv import load_dotenv
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange

# Wczytujemy zmienne środowiskowe z pliku .env
load_dotenv()

logging.basicConfig(level=logging.INFO)

async def get_common_pairs(exchange1, exchange2, session: aiohttp.ClientSession):
    pairs1 = await exchange1.get_trading_pairs(session)
    pairs2 = await exchange2.get_trading_pairs(session)
    common = set(pairs1) & set(pairs2)
    return list(common)

async def main():
    async with aiohttp.ClientSession() as session:
        # Tworzymy instancje giełd z użyciem kluczy API pobranych ze zmiennych środowiskowych
        binance = BinanceExchange(
            api_key=os.getenv("BINANCE_API_KEY"),
            secret=os.getenv("BINANCE_SECRET")
        )
        kucoin = KucoinExchange(
            api_key=os.getenv("KUCOIN_API_KEY"),
            secret=os.getenv("KUCOIN_SECRET")
        )

        # Wyznaczamy wspólne pary pomiędzy giełdami
        common_pairs = await get_common_pairs(binance, kucoin, session)
        logging.info(f"Wspólne pary między Binance a Kucoin: {common_pairs}")

        arbitrage_opportunities = []
        # Dla każdej wspólnej pary pobieramy ceny i sprawdzamy, czy występuje okazja arbitrażowa
        for pair in common_pairs:
            price_binance = await binance.get_price(pair, session)
            price_kucoin = await kucoin.get_price(pair, session)
            if price_binance is None or price_kucoin is None:
                continue

            # Obliczamy różnicę procentową
            if price_binance < price_kucoin:
                diff = ((price_kucoin - price_binance) / price_binance) * 100
                arbitrage_opportunities.append({
                    "pair": pair,
                    "buy": "Binance",
                    "sell": "Kucoin",
                    "price_buy": price_binance,
                    "price_sell": price_kucoin,
                    "difference_percent": diff
                })
            elif price_kucoin < price_binance:
                diff = ((price_binance - price_kucoin) / price_kucoin) * 100
                arbitrage_opportunities.append({
                    "pair": pair,
                    "buy": "Kucoin",
                    "sell": "Binance",
                    "price_buy": price_kucoin,
                    "price_sell": price_binance,
                    "difference_percent": diff
                })
        
        logging.info("Znalezione okazje arbitrażowe:")
        for opp in arbitrage_opportunities:
            logging.info(opp)

if __name__ == "__main__":
    asyncio.run(main())
