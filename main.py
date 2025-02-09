import asyncio
from config import CONFIG
from exchanges.binance import BinanceExchange
from exchanges.kucoin import KucoinExchange  # implementacja analogiczna do BinanceExchange
from exchanges.bitget import BitgetExchange  # implementacja analogiczna do BinanceExchange
from exchanges.bitstamp import BitstampExchange  # implementacja analogiczna do BinanceExchange
from arbitrage import ArbitrageStrategy

async def main():
    exchanges = {
        "binance": BinanceExchange(),
        "kucoin": KucoinExchange(),
        "bitget": BitgetExchange(),
        "bitstamp": BitstampExchange()
    }
    strategy = ArbitrageStrategy(exchanges)
    await strategy.run("BTC/USDT")

if __name__ == '__main__':
    asyncio.run(main())
