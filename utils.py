# utils.py
import logging

def normalize_symbol(symbol: str, exchange_name: str) -> str:
    """
    Normalizuje symbol do wspólnego formatu.
    Przykładowo:
      - Dla Bitget usuwa sufiks "_SPBL"
      - Dla Kucoin usuwa myślniki
    """
    symbol = symbol.upper()
    if exchange_name.lower() == "bitgetexchange":
        if symbol.endswith("_SPBL"):
            symbol = symbol[:-5]
    elif exchange_name.lower() == "kucoinexchange":
        symbol = symbol.replace("-", "")
    return symbol

def calculate_difference(price1: float, price2: float) -> float:
    """
    Oblicza procentową różnicę między dwoma cenami, względem niższej ceny.
    """
    if price1 == 0 or price2 == 0:
        logging.error("Jedna z cen jest równa 0 – nie można obliczyć różnicy.")
        return 0.0
    if price1 < price2:
        return ((price2 - price1) / price1) * 100
    else:
        return ((price1 - price2) / price2) * 100
