import json
import logging
import asyncio
from config import CONFIG
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Asynchroniczna funkcja pobierania rynków – wykorzystuje metodę load_markets()
async def get_markets_dict(exchange_instance, allowed_quotes=CONFIG["ALLOWED_QUOTES"]):
    try:
        logging.info(f"Loading markets for: {exchange_instance.__class__.__name__}")
        markets = await exchange_instance.load_markets()
        result = {}
        # Używamy pełnego symbolu jako klucza – dzięki temu "ABC/USDT" i "ABC/EUR" są traktowane oddzielnie
        for symbol in markets:
            if "/" in symbol:
                base, quote = symbol.split("/")
                if quote in allowed_quotes:
                    result[symbol] = symbol
        return result
    except Exception as e:
        logging.error(f"Error loading markets for {exchange_instance.__class__.__name__}: {e}")
        return {}

# Funkcja tworząca listę wspólnych aktywów dla pary giełd
async def get_common_assets_for_pair(name1, exchange1, name2, exchange2, allowed_quotes=CONFIG["ALLOWED_QUOTES"]):
    markets1 = await get_markets_dict(exchange1, allowed_quotes)
    markets2 = await get_markets_dict(exchange2, allowed_quotes)
    # Wspólne symbole traktujemy jako pełne symbole (np. "ABC/USDT" oddzielnie od "ABC/EUR")
    common_keys = set(markets1.keys()).intersection(set(markets2.keys()))
    common = {}
    for key in common_keys:
        common[key] = {name1: markets1[key], name2: markets2[key]}
    logging.info(f"Common assets for {name1} and {name2} (quotes={allowed_quotes}): {len(common)} found")
    return common

# Asynchroniczna funkcja sprawdzająca płynność dla danego symbolu na danej giełdzie
async def check_liquidity(exchange, symbol):
    try:
        order_book = await exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        if not bids or not asks:
            return False
        top_bid = bids[0]  # [price, volume]
        top_ask = asks[0]
        # Sprawdzamy, czy wolumen (volume) zarówno po stronie kupna, jak i sprzedaży przekracza MIN_LIQUIDITY
        if top_bid[1] >= CONFIG.get("MIN_LIQUIDITY", 50) and top_ask[1] >= CONFIG.get("MIN_LIQUIDITY", 50):
            return True
        return False
    except Exception as e:
        logging.error(f"Error checking liquidity for {symbol} on {exchange.__class__.__name__}: {e}")
        return False

# Funkcja filtrująca aktywa na podstawie płynności – sprawdza tylko te, które są wspólne dla danej pary giełd
async def filter_common_assets_by_liquidity(common_assets, exchange1, exchange2, name1, name2):
    filtered = {}
    tasks = []
    for symbol, mapping in common_assets.items():
        # Sprawdzamy płynność na obu giełdach równolegle
        tasks.append(asyncio.create_task(
            check_liquidity(exchange1, mapping[name1])
        ))
        tasks.append(asyncio.create_task(
            check_liquidity(exchange2, mapping[name2])
        ))
    results = await asyncio.gather(*tasks)
    # results zawiera kolejno dwa wyniki dla każdego symbolu (dla exchange1 i exchange2)
    symbols = list(common_assets.keys())
    for i, symbol in enumerate(symbols):
        liquidity_ex1 = results[2*i]
        liquidity_ex2 = results[2*i + 1]
        if liquidity_ex1 and liquidity_ex2:
            filtered[symbol] = common_assets[symbol]
    logging.info(f"After liquidity filtering, {len(filtered)} common assets remain.")
    return filtered

def save_common_assets(common_assets, filename="common_assets.json"):
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(common_assets, f, indent=4)
        logging.info(f"Common assets list saved to file: {filename}")
    except Exception as e:
        logging.error(f"Error saving to file {filename}: {e}")

def should_remove(asset, remove_list):
    for r in remove_list:
        if asset == r or asset.startswith(r + "/"):
            return True
    return False

async def modify_common_assets(common_assets, remove_file="assets_to_remove.json", add_file="assets_to_add.json"):
    try:
        with open(remove_file, "r", encoding="utf-8") as f:
            assets_to_remove = json.load(f)
        logging.info(f"Loaded assets to remove from {remove_file}.")
    except Exception as e:
        assets_to_remove = {}
        logging.warning(f"Failed to load {remove_file}: {e}")

    try:
        with open(add_file, "r", encoding="utf-8") as f:
            assets_to_add = json.load(f)
        logging.info(f"Loaded assets to add from {add_file}.")
    except Exception as e:
        assets_to_add = {}
        logging.warning(f"Failed to load {add_file}: {e}")

    for config_key in list(common_assets.keys()):
        if config_key in assets_to_remove:
            remove_list = assets_to_remove[config_key]
            before = len(common_assets[config_key])
            common_assets[config_key] = {asset: mapping for asset, mapping in common_assets[config_key].items()
                                         if not should_remove(asset, remove_list)}
            after = len(common_assets[config_key])
            logging.info(f"Configuration {config_key}: removed {before - after} assets.")
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
                    logging.info(f"Configuration {config_key}: added asset {entry}.")
    return common_assets

async def main():
    logging.info("Starting creation of common assets list (by full symbol and quote)")
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
            logging.info(f"Comparing assets for pair: {name1} - {name2}")
            mapping = await get_common_assets_for_pair(name1, exchanges[name1], name2, exchanges[name2],
                                                       allowed_quotes=CONFIG["ALLOWED_QUOTES"])
            # Filtrowanie aktywów na podstawie płynności – dla danej pary giełd
            mapping_filtered = await filter_common_assets_by_liquidity(mapping, exchanges[name1], exchanges[name2], name1, name2)
            common_assets[f"{name1}-{name2}"] = mapping_filtered

    common_assets = await modify_common_assets(common_assets)
    save_common_assets(common_assets)
    for pair, assets in common_assets.items():
        logging.info(f"Pair {pair} has {len(assets)} common assets.")
    
    # Zamykamy exchange
    await binance.close()
    await kucoin.close()
    await bitget.close()
    await bitstamp.close()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
