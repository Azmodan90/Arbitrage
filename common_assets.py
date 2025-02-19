import asyncio
import json
import logging
from config import CONFIG

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

async def load_markets_for_exchange(exchange, allowed_quotes):
    try:
        logger.info(f"Loading markets for: {exchange.__class__.__name__}")
        markets = await exchange.load_markets()
        result = {}
        for symbol in markets:
            if "/" in symbol:
                base, quote = symbol.split("/")
                if quote in allowed_quotes:
                    result[symbol] = symbol
        return result
    except Exception as e:
        logger.error(f"Error loading markets for {exchange.__class__.__name__}: {e}")
        return {}

async def get_total_volume(exchange, symbol, side='asks', levels=1):
    """
    Pobiera order book dla symbolu i sumuje wolumeny z pierwszych 'levels' pozycji po danej stronie (asks lub bids).
    """
    try:
        order_book = await exchange.fetch_order_book(symbol)
        levels_list = order_book.get(side, [])
        total_volume = sum(volume for price, volume in levels_list[:levels])
        return total_volume
    except Exception as e:
        logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return 0

async def get_common_assets_for_pair(name1, exchange1, name2, exchange2, allowed_quotes):
    """
    Pobiera rynki dla dwóch giełd i zwraca wspólne symbole (pełne symbole, np. "ABC/USDT" lub "ABC/EUR").
    Następnie – jeśli w CONFIG FILTER_LOW_LIQUIDITY=True – dla każdego symbolu sprawdza sumaryczny wolumen
    z pierwszych N pozycji order booka (ustalonych przez LIQUIDITY_LEVELS_TO_CHECK) dla obu giełd.
    Jeśli wolumen jest mniejszy niż minimalny (MIN_LIQUIDITY dla danego quote), symbol jest pomijany.
    """
    markets1 = await load_markets_for_exchange(exchange1, allowed_quotes)
    markets2 = await load_markets_for_exchange(exchange2, allowed_quotes)
    common_symbols = set(markets1.keys()).intersection(set(markets2.keys()))
    logger.info(f"Found {len(common_symbols)} common symbols for {name1} and {name2} before liquidity filtering")
    # Jeśli filtrowanie płynności jest włączone, odfiltrowujemy symbole
    if CONFIG.get("FILTER_LOW_LIQUIDITY", False):
        min_liq = CONFIG.get("MIN_LIQUIDITY", {})
        levels_to_check = CONFIG.get("LIQUIDITY_LEVELS_TO_CHECK", 1)
        filtered_symbols = set()
        for symbol in common_symbols:
            try:
                base, quote = symbol.split("/")
            except Exception as e:
                logger.error(f"Invalid symbol format {symbol}: {e}")
                continue
            required_liq = min_liq.get(quote, 0)
            vol1 = await get_total_volume(exchange1, symbol, side='asks', levels=levels_to_check)
            vol2 = await get_total_volume(exchange2, symbol, side='bids', levels=levels_to_check)
            if vol1 >= required_liq and vol2 >= required_liq:
                filtered_symbols.add(symbol)
            else:
                logger.info(f"Skipping {symbol} due to low liquidity: exchange1 asks: {vol1}, exchange2 bids: {vol2}, required: {required_liq}")
        common_symbols = filtered_symbols
        logger.info(f"{len(common_symbols)} common symbols remain for {name1} and {name2} after liquidity filtering")
    common = {}
    for symbol in common_symbols:
        common[symbol] = {name1: symbol, name2: symbol}
    return common

def save_common_assets(common_assets, filename="common_assets.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(common_assets, f, indent=4)
        logger.info(f"Common assets list saved to {filename}")
    except Exception as e:
        logger.error(f"Error saving to file {filename}: {e}")

def should_remove(asset, remove_list):
    for r in remove_list:
        if asset == r or asset.startswith(r + "/"):
            return True
    return False

async def modify_common_assets(common_assets, remove_file="assets_to_remove.json", add_file="assets_to_add.json"):
    try:
        with open(remove_file, "r", encoding="utf-8") as f:
            assets_to_remove = json.load(f)
        logger.info(f"Loaded assets to remove from {remove_file}.")
    except Exception as e:
        assets_to_remove = {}
        logger.warning(f"Failed to load {remove_file}: {e}")
    try:
        with open(add_file, "r", encoding="utf-8") as f:
            assets_to_add = json.load(f)
        logger.info(f"Loaded assets to add from {add_file}.")
    except Exception as e:
        assets_to_add = {}
        logger.warning(f"Failed to load {add_file}: {e}")
    for config_key in list(common_assets.keys()):
        if config_key in assets_to_remove:
            remove_list = assets_to_remove[config_key]
            before = len(common_assets[config_key])
            common_assets[config_key] = {asset: mapping for asset, mapping in common_assets[config_key].items()
                                         if not should_remove(asset, remove_list)}
            after = len(common_assets[config_key])
            logger.info(f"Configuration {config_key}: removed {before - after} assets.")
        if config_key in assets_to_add:
            add_entries = assets_to_add[config_key]
            if config_key not in common_assets:
                common_assets[config_key] = {}
            for entry in add_entries:
                normalized = entry.get("normalized")
                if normalized and normalized not in common_assets[config_key]:
                    common_assets[config_key][normalized] = {
                        config_key.split("-")[0]: entry.get("source"),
                        config_key.split("-")[1]: entry.get("dest")
                    }
                    logger.info(f"Configuration {config_key}: added asset {entry}.")
    return common_assets

async def main():
    logger.info("Starting creation of common assets list (by full symbol and quote)")
    from exchanges.binance import BinanceExchange
    from exchanges.kucoin import KucoinExchange
    from exchanges.bitget import BitgetExchange
    from exchanges.bitstamp import BitstampExchange
    binance = BinanceExchange()
    kucoin = KucoinExchange()
    bitget = BitgetExchange()
    bitstamp = BitstampExchange()
    exchanges = {
        "binance": binance,
        "kucoin": kucoin,
        "bitget": bitget,
        "bitstamp": bitstamp
    }
    common_assets = {}
    names = list(exchanges.keys())
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            name1 = names[i]
            name2 = names[j]
            logger.info(f"Comparing assets for pair: {name1} - {name2}")
            mapping = await get_common_assets_for_pair(name1, exchanges[name1], name2, exchanges[name2], allowed_quotes=CONFIG["ALLOWED_QUOTES"])
            common_assets[f"{name1}-{name2}"] = mapping
    common_assets = await modify_common_assets(common_assets)
    save_common_assets(common_assets)
    for pair, assets in common_assets.items():
        logger.info(f"Pair {pair} has {len(assets)} common assets.")
    await binance.close()
    await kucoin.close()
    await bitget.close()
    await bitstamp.close()

if __name__ == '__main__':
    asyncio.run(main())
