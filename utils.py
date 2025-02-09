import difflib
import re

def normalize_symbol(symbol, exchange_name: str) -> str:
    """
    Normalizuje symbol, aby jednoznacznie zidentyfikować projekt.
    Jeśli symbol jest słownikiem, próbuje użyć pola 'base' (lub łączy 'base' i 'quote').
    Następnie – po usunięciu ewentualnej końcówki (np. USDT, USD) oraz znaków specjalnych –
    dokonuje mapowania (np. XBT → BTC) oraz zwraca unikalny identyfikator, np. "bitcoin".
    """
    if isinstance(symbol, dict):
        base = symbol.get("base")
        if base:
            symbol = base
        else:
            symbol = symbol.get("symbol") or (symbol.get("base", "") + symbol.get("quote", ""))
    
    symbol = symbol.upper().strip()
    # Usuwamy znane końcówki kwotowane
    known_quotes = ["USDT", "USD", "USDC", "EUR"]
    for quote in known_quotes:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            symbol = symbol[:-len(quote)]
            break
    
    # Usuwamy znaki inne niż alfanumeryczne
    norm = re.sub(r'[^A-Z0-9]', '', symbol)
    
    # Mapowanie rozbieżności
    mapping = {
        "XBT": "BTC",
        "BCC": "BCH",
    }
    norm = mapping.get(norm, norm)
    
    # Znane projekty – jeśli norm odpowiada wpisowi, zwracamy unikalny identyfikator
    known_projects = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "LTC": "litecoin",
        "BNB": "binancecoin",
        "ADA": "cardano",
        "SOL": "solana",
    }
    if norm in known_projects:
        return known_projects[norm]
    
    matches = difflib.get_close_matches(norm, known_projects.keys(), n=1, cutoff=0.8)
    if matches:
        return known_projects[matches[0]]
    return norm

def calculate_difference(price1: float, price2: float) -> float:
    """
    Oblicza procentową różnicę między dwiema cenami względem ceny bazowej.
    """
    if price1 == 0:
        return 0.0
    return abs(((price2 - price1) / price1) * 100)
