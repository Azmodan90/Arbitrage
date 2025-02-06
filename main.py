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

# Konfiguracja logowania: logi będą zapisywane w konsoli oraz do pliku app.log
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

def normalize_symbol(symbol: str, exchange_name: str) -> str:
    """
    Normalizuje symbol do wspólnego formatu (np. "BTCUSDT").
    Dla giełdy Bitget usuwa sufiks "_SPBL".
    Dla giełdy Kucoin usuwa myślnik.
    Dla pozostałych zakłada, że symbol już jest w odpowiednim formacie.
    """
    symbol = symbol.upper()
    if exchange_name == "BitgetExchange":
        if symbol.endswith("_SPBL"):
            symbol = symbol[:-5]  # usuwa 5 znaków: "_SPBL"
    elif exchange_name == "KucoinExchange":
        symbol = symbol.replace("-", "")
    return symbol

async def get_common_pairs(exchange1, exchange2, session: aiohttp.ClientSession):
    """
    Pobiera listy par z dwóch giełd, normalizuje symbole i wyznacza ich przecięcie.
    Zwraca listę krotek: (oryginalny_symbol_ex1, oryginalny_symbol_ex2, normalized_symbol)
    """
    pairs1 = await exchange1.get_trading_pairs(session)
    pairs2 = await exchange2.get_trading_pairs(session)
    # Tworzymy mapę: normalized -> oryginalny symbol, dla każdej giełdy
    mapping1 = {normalize_symbol(sym, exchange1.__class__.__name__): sym for sym in pairs1}
    mapping2 = {normalize_symbol(sym, exchange2.__class__.__name__): sym for sym in pairs2}
    common_norm = set(mapping1.keys()) & set(mapping2.keys())
    common_list = []
    for norm in common_norm:
        common_list.append((mapping1[norm], mapping2[norm], norm))
    logging.info(f"Wspólne pary (normalized): {common_norm}")
    return common_list

def calculate_difference(price1: float, price2: float) -> float:
    """
    Oblicza procentową różnicę między dwiema cenami, stosując wzór w stosunku do niższej z nich.
    """
    if price1 < price2:
        return ((price2 - price1) / price1) * 100
    else:
        return ((price1 - price2) / price2) * 100

async def main():
    async with aiohttp.ClientSession() as session:
        # Inicjalizacja giełd – klucze API pobieramy z .env
        binance = BinanceExchange(api_key=os.getenv("BINANCE_API_KEY"), secret=os.getenv("BINANCE_SECRET"))
        kucoin = KucoinExchange(api_key=os.getenv("KUCOIN_API_KEY"), secret=os.getenv("KUCOIN_SECRET"))
        bitget = BitgetExchange(api_key=os.getenv("BITGET_API_KEY"), secret=os.getenv("BITGET_SECRET"))
        bitstamp = BitstampExchange(api_key=os.getenv("BITSTAMP_API_KEY"), secret=os.getenv("BITSTAMP_SECRET"))
        
        # Przykładowo: wyznaczamy wspólne pary między Bitget a Bitstamp
        common_pairs = await get_common_pairs(bitget, bitstamp, session)
        if not common_pairs:
            logging.warning("Brak wspólnych par między Bitget a Bitstamp.")
        else:
            logging.info(f"Znaleziono wspólne pary: {common_pairs}")

        arbitrage_opportunities = []
        # Dla każdej wspólnej pary pobieramy ceny z obu giełd używając oryginalnych symboli
        for original_bitget, original_bitstamp, norm in common_pairs:
            price_bitget = await bitget.get_price(original_bitget, session)
            price_bitstamp = await bitstamp.get_price(original_bitstamp, session)
            logging.info(f"Ceny dla {norm}: Bitget ({original_bitget}) = {price_bitget}, Bitstamp ({original_bitstamp}) = {price_bitstamp}")
            if price_bitget is None or price_bitstamp is None:
                logging.error(f"Nie udało się pobrać ceny dla {norm}")
                continue

            diff = calculate_difference(price_bitget, price_bitstamp)
            if diff >= 1.0:  # Próg 1% – można dostosować
                if price_bitget < price_bitstamp:
                    arbitrage_opportunities.append({
                        "pair": norm,
                        "buy": "Bitget",
                        "sell": "Bitstamp",
                        "price_buy": price_bitget,
                        "price_sell": price_bitstamp,
                        "difference_percent": diff
                    })
                    logging.info(f"Okazja arbitrażowa: Kup {norm} na Bitget po {price_bitget:.2f}, sprzedaj na Bitstamp po {price_bitstamp:.2f} - różnica: {diff:.2f}%")
                else:
                    arbitrage_opportunities.append({
                        "pair": norm,
                        "buy": "Bitstamp",
                        "sell": "Bitget",
                        "price_buy": price_bitstamp,
                        "price_sell": price_bitget,
                        "difference_percent": diff
                    })
                    logging.info(f"Okazja arbitrażowa: Kup {norm} na Bitstamp po {price_bitstamp:.2f}, sprzedaj na Bitget po {price_bitget:.2f} - różnica: {diff:.2f}%")
        
        if arbitrage_opportunities:
            logging.info("Znalezione okazje arbitrażowe:")
            for opp in arbitrage_opportunities:
                logging.info(opp)
        else:
            logging.info("Brak okazji arbitrażowych.")

if __name__ == "__main__":
    asyncio.run(main())
