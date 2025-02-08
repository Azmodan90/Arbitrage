import difflib

def normalize_symbol(symbol, exchange_name: str) -> str:
    """
    Normalizuje symbol, aby jednoznacznie zidentyfikować projekt (zazwyczaj walutę bazową).
    
    Jeśli symbol jest słownikiem (np. z Binance), używa pola 'base'.
    Jeśli symbol jest stringiem, próbuje wykryć, czy kończy się na jeden z znanych symboli walut kwotowanych
    (np. USDT, USD, USDC, EUR) i zwraca część odpowiadającą walucie bazowej.
    
    Argumenty:
        symbol -- symbol pobrany z API giełdy (string lub dict),
        exchange_name -- nazwa giełdy (np. 'BinanceExchange').
    
    Zwraca:
        Unikalny identyfikator projektu (string), np. "BTC" lub, przy mapowaniu, "bitcoin".
    """
    # Jeśli symbol jest słownikiem, wykorzystaj pole 'base'
    if isinstance(symbol, dict):
        base = symbol.get("base")
        if base:
            symbol = base
        else:
            # W razie braku pola 'base', scal 'base' i 'quote'
            symbol = symbol.get("symbol") or f"{symbol.get('base', '')}{symbol.get('quote', '')}"

    # Jeśli symbol jest stringiem, spróbuj wyodrębnić walutę bazową, jeśli kończy się na znany quote
    known_quotes = ["USDT", "USD", "USDC", "EUR"]
    orig_symbol = symbol  # zachowaj oryginalny symbol dla ewentualnego fallback
    symbol = symbol.upper().strip()
    for quote in known_quotes:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            # Wyodrębnij część przed końcówką quote
            symbol = symbol[:-len(quote)]
            break  # zakładamy, że tylko jeden quote pasuje

    # Usuń wszelkie znaki niedozwolone (tylko alfanumeryczne)
    norm = ''.join(filter(str.isalnum, symbol))

    # Mapowanie znanych rozbieżności – np. zamiana XBT na BTC
    mapping = {
        "XBT": "BTC",
        "BCC": "BCH",
        # Dodaj kolejne mapowania wg potrzeb
    }
    norm = mapping.get(norm, norm)
    
    # Słownik projektów – kluczem może być skrót, a wartością unikalny identyfikator
    known_projects = {
        "BTC": "bitcoin",
        "ETH": "ethereum",
        "LTC": "litecoin",
        "BNB": "binancecoin",
        "ADA": "cardano",
        "SOL": "solana",
        # Dodaj kolejne wpisy według potrzeb
    }
    
    # Jeśli norm dokładnie odpowiada wpisowi, zwróć unikalny identyfikator
    if norm in known_projects:
        return known_projects[norm]
    
    # Jeśli nie, spróbuj fuzzy matching
    matches = difflib.get_close_matches(norm, known_projects.keys(), n=1, cutoff=0.8)
    if matches:
        return known_projects[matches[0]]
    
    # Jeśli nadal nie rozpoznano, zwróć oryginalny (normalizowany) symbol
    return norm
