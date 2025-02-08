# utils.py
import logging

def normalize_symbol(asset_info, exchange_name: str) -> str:
    """
    Normalizuje symbol do wspólnego formatu, sprawdzając także inne dane:
    - Symbol
    - Nazwę pełną
    - Base i Quote asset
    - Adres kontraktu (jeśli dostępny)
    """
    if isinstance(asset_info, dict):
        symbol = asset_info.get("symbol", "").upper()
        full_name = asset_info.get("name", "").lower()
        base_asset = asset_info.get("baseAsset", "").upper()
        quote_asset = asset_info.get("quoteAsset", "").upper()
        contract_address = asset_info.get("contractAddress", "").lower()
    else:
        symbol = str(asset_info).upper()
        full_name = ""
        base_asset = ""
        quote_asset = ""
        contract_address = ""

    if exchange_name.lower() == "bitgetexchange":
        symbol = symbol.replace("_SPBL", "")
    elif exchange_name.lower() == "kucoinexchange":
        symbol = symbol.replace("-", "")

    return f"{symbol}-{full_name}-{base_asset}/{quote_asset}-{contract_address}"

def calculate_difference(price1: float, price2: float) -> float:
    """
    Oblicza procentową różnicę między dwoma cenami, względem niższej ceny.
    """
    if price1 == 0 or price2 == 0:
        logging.error("Jedna z cen jest równa 0 – nie można obliczyć różnicy.")
        return 0.0
    return abs(((price2 - price1) / price1) * 100)
