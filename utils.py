import logging

def normalize_symbol(asset_info, exchange_name: str) -> str:
    """
    Normalizuje dane dotyczące aktywa do postaci unikalnego klucza.
    Jeśli dostępny jest adres kontraktu (np. dla tokenów), zostanie on użyty jako główny identyfikator,
    ponieważ jest unikalny dla danego projektu.
    W przeciwnym razie budujemy klucz na podstawie:
      - symbolu (po ewentualnej modyfikacji specyficznej dla giełdy),
      - pełnej nazwy (jeśli dostępna),
      - pary bazowej/cytowanej.
    Dzięki temu unikamy problemu, gdy kilka aktywów ma ten sam symbol, a są to różne projekty,
    lub gdy ten sam projekt jest oznaczony nieco inaczej na różnych platformach.
    """
    # Jeśli asset_info to słownik, pobieramy poszczególne dane
    if isinstance(asset_info, dict):
        contract_address = asset_info.get("contractAddress", "").strip().lower()
        # Jeśli dostępny jest adres kontraktu, zwróć go – to jednoznaczny identyfikator
        if contract_address:
            return contract_address

        symbol   = asset_info.get("symbol", "").upper().strip()
        full_name = asset_info.get("name", "").lower().strip()
        base_asset  = asset_info.get("baseAsset", "").upper().strip()
        quote_asset = asset_info.get("quoteAsset", "").upper().strip()
    else:
        symbol   = str(asset_info).upper().strip()
        full_name = ""
        base_asset  = ""
        quote_asset = ""
        contract_address = ""

    # Modyfikacje specyficzne dla danej giełdy
    if exchange_name.lower() == "bitgetexchange":
        symbol = symbol.replace("_SPBL", "")
    elif exchange_name.lower() == "kucoinexchange":
        symbol = symbol.replace("-", "")

    # Budujemy klucz – w tym przypadku łączymy symbol, pełną nazwę i parę (base/quote)
    # (możesz modyfikować ten wzorzec według potrzeb, aby jeszcze lepiej rozróżniać aktywa)
    key = f"{symbol}-{full_name}-{base_asset}/{quote_asset}"
    return key


def calculate_difference(price1: float, price2: float) -> float:
    """
    Oblicza procentową różnicę między dwoma cenami względem ceny bazowej (price1).
    """
    if price1 == 0 or price2 == 0:
        logging.error("Jedna z cen jest równa 0 – nie można obliczyć różnicy.")
        return 0.0
    return abs(((price2 - price1) / price1) * 100)
