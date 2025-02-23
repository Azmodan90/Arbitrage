import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate

from logging.handlers import RotatingFileHandler

# Konfiguracja loggerów z RotatingFileHandler
def setup_logger(logger_name, log_file, level=logging.INFO):
    logger = logging.getLogger(logger_name)
    if not logger.hasHandlers():
        handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger

arbitrage_logger = setup_logger("arbitrage", "arbitrage.log")
opp_logger = setup_logger("arbitrage_opportunities", "arbitrage_opportunities.log")
unprofitable_logger = setup_logger("unprofitable_opportunities", "unprofitable_opportunities.log")
absurd_logger = setup_logger("absurd_opportunities", "absurd_opportunities.log")

def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# Asynchroniczny rate limiter – działający przy użyciu asyncio.sleep()
class RateLimiter:
    def __init__(self, delay):
        self.delay = delay  # minimalny odstęp między zapytaniami (w sekundach)
        self.last_request = 0

RATE_LIMITS = {
    "binanceexchange": 0.05,
    "kucoinexchange": 0.2,
    "bitgetexchange": 0.3,
    "bitstampexchange": 1.2
}
rate_limiters = {}

def get_rate_limiter(exchange):
    key = exchange.__class__.__name__.lower()
    if key not in rate_limiters:
        delay = RATE_LIMITS.get(key, 0.1)
        rate_limiters[key] = RateLimiter(delay)
    return rate_limiters[key]

async def fetch_ticker_rate_limited_async(exchange, symbol):
    now = time.monotonic()
    limiter = get_rate_limiter(exchange)
    wait_time = limiter.delay - (now - limiter.last_request)
    if wait_time > 0:
        await asyncio.sleep(wait_time)
    ticker = await exchange.fetch_ticker(symbol)
    limiter.last_request = time.monotonic()
    return ticker

# Zmieniamy get_liquidity_info_async, aby zwracał cały order book
async def get_liquidity_info_async(exchange, symbol):
    try:
        order_book = await exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        return {"bids": bids, "asks": asks}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

# Funkcja agregująca kilka poziomów order booka – oblicza średnią ważoną cenę dla wymaganej ilości
def aggregate_order_book(levels, required_qty):
    total_cost = 0
    accumulated_qty = 0
    for price, volume in levels:
        if volume is None:
            continue
        if accumulated_qty + volume >= required_qty:
            qty_needed = required_qty - accumulated_qty
            total_cost += qty_needed * price
            accumulated_qty += qty_needed
            break
        else:
            total_cost += volume * price
            accumulated_qty += volume
    if accumulated_qty == 0:
        return None
    return total_cost / accumulated_qty

# Funkcja sumująca całkowity dostępny wolumen na wszystkich poziomach
def total_volume(levels):
    return sum(volume for _, volume in levels if volume is not None)

# Funkcja konwersji inwestycji – przelicza INVESTMENT_AMOUNT (w USDT) na jednostki quote
async def convert_investment(quote, investment_usdt, conversion_exchange):
    pair = f"{quote}/USDT"
    ticker = await conversion_exchange.fetch_ticker(pair)
    if ticker is None or ticker.get("last") is None:
        return investment_usdt
    price = ticker.get("last")
    return investment_usdt / price

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        # assets – słownik z pełnymi symbolami, np. { "ABC/USDT": {"binance": "ABC/USDT", "bitget": "ABC/USDT"} }
        self.assets = assets
        self.pair_name = pair_name  # np. "binance-bitget"

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        if not isinstance(asset, dict):
            if "/" in asset:
                asset = {names[0]: asset, names[1]: asset}
            else:
                arbitrage_logger.error(f"{self.pair_name} - Asset '{asset}' does not contain '/', skipping.")
                return

        symbol_ex1 = asset.get(names[0])
        symbol_ex2 = asset.get(names[1])
        if not symbol_ex1 or not symbol_ex2:
            arbitrage_logger.warning(f"{self.pair_name} - Incomplete symbol data for asset {asset}, skipping.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Checking arbitrage for symbols: {symbol_ex1} ({names[0]}), {symbol_ex2} ({names[1]})")
        try:
            ticker1 = await fetch_ticker_rate_limited_async(self.exchange1, symbol_ex1)
            ticker2 = await fetch_ticker_rate_limited_async(self.exchange2, symbol_ex2)
        except asyncio.CancelledError:
            return

        tickers = {}
        if ticker1:
            price1 = ticker1.get('last')
            if price1 is None:
                arbitrage_logger.warning(f"{self.pair_name} - Ticker price for {names[0]} is None, skipping asset {asset}")
            else:
                tickers[names[0]] = price1
                arbitrage_logger.info(f"{self.pair_name} - Ticker {names[0]}: {price1}")
        if ticker2:
            price2 = ticker2.get('last')
            if price2 is None:
                arbitrage_logger.warning(f"{self.pair_name} - Ticker price for {names[1]} is None, skipping asset {asset}")
            else:
                tickers[names[1]] = price2
                arbitrage_logger.info(f"{self.pair_name} - Ticker {names[1]}: {price2}")
        if names[0] not in tickers or names[1] not in tickers:
            arbitrage_logger.warning(f"{self.pair_name} - Insufficient ticker data for {asset}, skipping.")
            return

        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        effective_buy_ex1 = tickers[names[0]] * (1 + fee1 / 100)
        effective_sell_ex2 = tickers[names[1]] * (1 - fee2 / 100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = tickers[names[1]] * (1 + fee2 / 100)
        effective_sell_ex1 = tickers[names[0]] * (1 - fee1 / 100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        try:
            quote = symbol_ex1.split("/")[1]
        except Exception as e:
            arbitrage_logger.error(f"{self.pair_name} - Error determining quote from symbol {symbol_ex1}: {e}")
            return

        base_investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        investment = base_investment
        if CONFIG.get("CONVERT_INVESTMENT", {}).get(quote, False):
            from exchanges.binance import BinanceExchange
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for quote {quote}: {base_investment} USDT -> {investment:.6f} {quote}")

        profit_liq = None
        invested_amount = None
        actual_qty = None
        liquidity_info = "N/D"
        extra_info = ""
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            liq_ex1 = await get_liquidity_info_async(self.exchange1, symbol_ex1)
            liq_ex2 = await get_liquidity_info_async(self.exchange2, symbol_ex2)
            liquidity_info = ""
            if liq_ex1:
                liquidity_info += f"{names[0]} Asks: {liq_ex1['asks']}; "
            if liq_ex2:
                liquidity_info += f"{names[1]} Bids: {liq_ex2['bids']}"
            if liq_ex1 and liq_ex2:
                ask_levels = liq_ex1.get('asks', [])
                bid_levels = liq_ex2.get('bids', [])
                total_ask_volume = sum(level[1] for level in ask_levels if level[1] is not None)
                total_bid_volume = sum(level[1] for level in bid_levels if level[1] is not None)
                # Obliczamy maksymalny możliwy do zrealizowania wolumen (na podstawie sumy wolumenów)
                max_qty = min(total_ask_volume, total_bid_volume)
                desired_qty = investment / effective_buy_ex1
                actual_qty = min(desired_qty, max_qty)
                agg_buy_price = aggregate_order_book(ask_levels, actual_qty)
                agg_sell_price = aggregate_order_book(bid_levels, actual_qty)
                if agg_buy_price is None or agg_sell_price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - Unable to aggregate order book for {asset}, skipping.")
                    return
                potential_proceeds = actual_qty * agg_sell_price
                invested_amount = actual_qty * agg_buy_price
                profit_liq = potential_proceeds - invested_amount
                profit_liq_percent = (profit_liq / invested_amount * 100) if invested_amount else 0
                extra_info += f"Qty: {actual_qty:.4f}; Invested: {invested_amount:.6f} {quote}; Proceeds: {potential_proceeds:.6f} {quote}; "
                if total_ask_volume < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[0]} (total ask volume: {total_ask_volume}); "
                if total_bid_volume < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[1]} (total bid volume: {total_bid_volume}); "
            else:
                extra_info = "No liquidity data available."
        else:
            extra_info = "No liquidity check (threshold not met)."

        try:
            log_line = (
                f"Pair: {self.pair_name} | Asset: {asset} | "
                f"Buy ({names[0]} eff.): {effective_buy_ex1:.4f} | Sell ({names[1]} eff.): {effective_sell_ex2:.4f} | "
                f"Ticker Profit: {profit1:.2f}% | Liquidity Profit: {f'{profit_liq_percent:.2f}' if 'profit_liq_percent' in locals() and profit_liq_percent is not None else 'N/A'}% | "
                f"Profit ({quote}): {f'{profit_liq:.6f}' if profit_liq is not None else 'N/A'} | "
                f"Invested ({quote}): {f'{invested_amount:.6f}' if invested_amount is not None else 'N/A'} | "
                f"Qty Purchased: {f'{actual_qty:.4f}' if actual_qty is not None else 'N/A'} | "
                f"Liquidity Info: {liquidity_info} | Extra: {extra_info}"
            )
        except Exception as format_e:
            arbitrage_logger.error(f"{self.pair_name} - Formatting error: {format_e}")
            return

        if profit_liq is not None and profit_liq > 0:
            opp_logger.info(log_line)
        else:
            unprofitable_logger.info(log_line)

        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(
                f"{self.pair_name} - Opportunity: Buy on {self.exchange1.__class__.__name__} (price: {tickers[names[0]]}, eff.: {effective_buy_ex1:.4f}) | "
                f"Sell on {self.exchange2.__class__.__name__} (price: {tickers[names[1]]}, eff.: {effective_sell_ex2:.4f}) | "
                f"Ticker Profit: {profit1:.2f}% | Profit: {f'{profit_liq:.6f}' if profit_liq is not None else 'N/A'} {quote}"
            )
        if profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(
                f"{self.pair_name} - Opportunity: Buy on {self.exchange2.__class__.__name__} (price: {tickers[names[1]]}, eff.: {effective_buy_ex2:.4f}) | "
                f"Sell on {self.exchange1.__class__.__name__} (price: {tickers[names[0]]}, eff.: {effective_sell_ex1:.4f}) | "
                f"Ticker Profit: {profit2:.2f}%"
            )

    async def run(self):
        arbitrage_logger.info(f"{self.pair_name} - Starting arbitrage strategy for {len(self.assets)} assets.")
        try:
            while True:
                for asset in self.assets:
                    await self.check_opportunity(asset)
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            arbitrage_logger.info(f"{self.pair_name} - Arbitrage strategy cancelled.")
            return

# Funkcja agregująca kilka poziomów order booka – oblicza średnią ważoną cenę dla wymaganej ilości
def aggregate_order_book(levels, required_qty):
    total_cost = 0
    accumulated_qty = 0
    for price, volume in levels:
        if volume is None:
            continue
        if accumulated_qty + volume >= required_qty:
            qty_needed = required_qty - accumulated_qty
            total_cost += qty_needed * price
            accumulated_qty += qty_needed
            break
        else:
            total_cost += volume * price
            accumulated_qty += volume
    if accumulated_qty == 0:
        return None
    return total_cost / accumulated_qty

if __name__ == '__main__':
    # For testing purposes – normally the strategy is launched via common_assets
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
