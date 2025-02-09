import json
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange
from exchanges.bitget import BitgetExchange
from exchanges.bitstamp import BitstampExchange

def load_coingecko_tokens():
    with open("coingecko_tokens.json", "r") as f:
        tokens = json.load(f)
    # Tworzymy mapę: symbol (wielkie litery) -> coin id
    mapping = {}
    for token in tokens:
        sym = token["symbol"].upper()
        if sym not in mapping:
            mapping[sym] = token["id"]
    return mapping

def generate_common_assets():
    # Inicjalizacja giełd
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
    
    coin_mapping = load_coingecko_tokens()
    
    common_assets = {}
    # Iterujemy po parach giełd
    exchange_names = list(exchanges.keys())
    for i in range(len(exchange_names)):
        for j in range(i + 1, len(exchange_names)):
            ex1 = exchanges[exchange_names[i]]
            ex2 = exchanges[exchange_names[j]]
            markets1 = ex1.exchange.load_markets()
            markets2 = ex2.exchange.load_markets()
            tokens1 = {market.split("/")[0].upper() for market in markets1}
            tokens2 = {market.split("/")[0].upper() for market in markets2}
            # Zamieniamy symbole na coin id według CoinGecko
            coin_ids1 = {sym: coin_mapping.get(sym, sym) for sym in tokens1}
            coin_ids2 = {sym: coin_mapping.get(sym, sym) for sym in tokens2}
            # Wspólne coin id
            common = set(coin_ids1.values()).intersection(set(coin_ids2.values()))
            # Zapisujemy wynik
            pair_key = f"{exchange_names[i]}-{exchange_names[j]}"
            common_assets[pair_key] = list(common)
    with open("common_assets.json", "w") as f:
        json.dump(common_assets, f, indent=4)
    print("Zapisano listę wspólnych aktywów do common_assets.json")

if __name__ == "__main__":
    generate_common_assets()
