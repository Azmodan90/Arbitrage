import json
import logging
from config import CONFIG
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def get_markets_dict(exchange_instance, allowed_quotes=["USDT"]):
    try:
        logging.info(f"Loading markets for: {exchange_instance.__class__.__name__}")
        markets = await exchange_instance.load_markets()
        result = {}
        for symbol in markets:
            if "/" in symbol:
                base, quote = symbol.split("/")
                if quote in allowed_quotes:
                    # Używamy pełnego symbolu jako klucza, np. "ABC/USDT" lub "ABC/EUR"
                    result[symbol] = symbol
        return result
    except Exception as e:
        logging.error(f"Error loading markets for {exchange_instance.__class__.__name__}: {e}")
        return {}

async def get_common_assets_for_pair(name1, exchange1, name2, exchange2, allowed_quotes=["USDT"]):
    markets1 = await get_markets_dict(exchange1, allowed_quotes)
    markets2 = await get_markets_dict(exchange2, allowed_quotes)
    # Wykorzystujemy pełne symbole jako klucze – dzięki temu "ABC/USDT" i "ABC/EUR" są różne
    common_keys = set(markets1.keys()).intersection(set(markets2.keys()))
    common = {}
    for key in common_keys:
         common[key] = {name1: markets1[key], name2: markets2[key]}
    logging.info(f"Common assets for {name1} and {name2} (quotes={allowed_quotes}): {len(common)} found")
    return common

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
    logging.info("Starting creation of common assets list (by symbol and quote)")
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
            mapping = await get_common_assets_for_pair(name1, exchanges[name1], name2, exchanges[name2], allowed_quotes=CONFIG["ALLOWED_QUOTES"])
            common_assets[f"{name1}-{name2}"] = mapping

    common_assets = await modify_common_assets(common_assets)
    save_common_assets(common_assets)
    for pair, assets in common_assets.items():
        logging.info(f"Pair {pair} has {len(assets)} common assets.")
    
    # Close exchanges
    await binance.close()
    await kucoin.close()
    await bitget.close()
    await bitstamp.close()

if __name__ == '__main__':
    import asyncio
    from config import CONFIG
    asyncio.run(main())
