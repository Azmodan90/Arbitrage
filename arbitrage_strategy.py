# arbitrage_strategy.py
import asyncio
import aiohttp
import logging
from utils import calculate_difference

async def run_arbitrage(common_pairs, exchange_mapping, threshold: float = 1.0):
    """
    Dla każdej wspólnej pary pobiera ceny z dwóch giełd i sprawdza, czy występuje okazja arbitrażowa.
    
    :param common_pairs: Lista krotek (symbol_ex1, symbol_ex2, normalized_symbol)
    :param exchange_mapping: Słownik {nazwa_giełdy: instancja_giełdy} – dokładnie dla dwóch giełd.
    :param threshold: Minimalna różnica procentowa, aby uznać okazję za arbitrażową.
    """
    async with aiohttp.ClientSession() as session:
        arbitrage_opportunities = []
        for pair in common_pairs:
            original_symbol_ex1, original_symbol_ex2, normalized_symbol = pair
            # Załóżmy, że mamy dokładnie dwie giełdy:
            exchange_names = list(exchange_mapping.keys())
            if len(exchange_names) != 2:
                logging.error("Strategia arbitrażu wspiera tylko dwie giełdy.")
                return
            exch1_name = exchange_names[0]
            exch2_name = exchange_names[1]
            exch1 = exchange_mapping[exch1_name]
            exch2 = exchange_mapping[exch2_name]

            # Pobieramy ceny równolegle
            price1, price2 = await asyncio.gather(
                exch1.get_price(original_symbol_ex1, session),
                exch2.get_price(original_symbol_ex2, session)
            )
            logging.info(f"Ceny dla {normalized_symbol}: {exch1_name} ({original_symbol_ex1}) = {price1}, {exch2_name} ({original_symbol_ex2}) = {price2}")
            if price1 is None or price2 is None or price1 == 0 or price2 == 0:
                logging.error(f"Pomijam {normalized_symbol} z powodu błędnych danych cenowych.")
                continue

            diff = calculate_difference(price1, price2)
            if diff >= threshold:
                if price1 < price2:
                    opp = {
                        "pair": normalized_symbol,
                        "buy": exch1_name,
                        "sell": exch2_name,
                        "price_buy": price1,
                        "price_sell": price2,
                        "difference_percent": diff
                    }
                    logging.info(f"Okazja arbitrażowa: Kup {normalized_symbol} na {exch1_name} po {price1}, sprzedaj na {exch2_name} po {price2} (różnica: {diff:.2f}%)")
                else:
                    opp = {
                        "pair": normalized_symbol,
                        "buy": exch2_name,
                        "sell": exch1_name,
                        "price_buy": price2,
                        "price_sell": price1,
                        "difference_percent": diff
                    }
                    logging.info(f"Okazja arbitrażowa: Kup {normalized_symbol} na {exch2_name} po {price2}, sprzedaj na {exch1_name} po {price1} (różnica: {diff:.2f}%)")
                arbitrage_opportunities.append(opp)
        if arbitrage_opportunities:
            logging.info("Znalezione okazje arbitrażowe:")
            for opp in arbitrage_opportunities:
                logging.info(opp)
        else:
            logging.info("Brak okazji arbitrażowych.")
