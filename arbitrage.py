import asyncio
import logging
import json
import time
from logging.handlers import RotatingFileHandler
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate

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

# Asynchroniczny rate limiter – oparty o asyncio.sleep()
class RateLimiter:
    def __init__(self, delay):
        self.delay = delay
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

# Funkcja obliczająca ważoną średnią cenę z kilku poziomów order booka
def compute_weighted_average_price(order_book, desired_qty, side='ask', fee=0):
    orders = order_book.get('asks', []) if side=='ask' else order_book.get('bids', [])
    total_qty = 0
    weighted_sum = 0
    breakdown = []  # lista (price, qty_used) dla każdego poziomu
    max_levels = CONFIG.get("ORDERBOOK_LEVELS", len(orders))
    for order in orders[:max_levels]:
        price, vol = order
        if total_qty + vol >= desired_qty:
            vol_used = desired_qty - total_qty
            weighted_sum += price * vol_used
            breakdown.append((price, vol_used))
            total_qty = desired_qty
            break
        else:
            weighted_sum += price * vol
            breakdown.append((price, vol))
            total_qty += vol
    if total_qty == 0:
        return None, []
    weighted_price = weighted_sum / total_qty
    # Uwzględnienie opłaty: przy kupnie (asks) dodajemy fee, przy sprzedaży (bids) odejmujemy fee
    weighted_price *= (1 + fee/100) if side=='ask' else (1 - fee/100)
    return weighted_price, breakdown

async def get_liquidity_info_async(exchange, symbol):
    try:
        order_book = await exchange.fetch_order_book(symbol)
        # Ograniczenie liczby poziomów z order booka, jeśli ustawiono
        max_levels = CONFIG.get("ORDERBOOK_LEVELS", None)
        if max_levels is not None:
            order_book['asks'] = order_book.get('asks', [])[:max_levels]
            order_book['bids'] = order_book.get('bids', [])[:max_levels]
        return order_book
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

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
        self.assets = assets
        self.pair_name = pair_name

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

        # Pobieramy order booki ograniczone do kilku poziomów
        liq_ex1 = await get_liquidity_info_async(self.exchange1, symbol_ex1)
        liq_ex2 = await get_liquidity_info_async(self.exchange2, symbol_ex2)

        weighted_buy_price = None
        weighted_sell_price = None
        breakdown_buy = []
        breakdown_sell = []
        if liq_ex1 and liq_ex2:
            # Ustalamy początkowo zamawianą ilość (na podstawie tickerowej ceny)
            desired_qty = investment / effective_buy_ex1
            # Dla kupna (asks) obliczamy ważoną średnią z wykorzystaniem kilku poziomów:
            weighted_buy_price, breakdown_buy = compute_weighted_average_price(liq_ex1, desired_qty, side='ask', fee=fee1)
            # Dla sprzedaży (bids):
            weighted_sell_price, breakdown_sell = compute_weighted_average_price(liq_ex2, desired_qty, side='bid', fee=fee2)
        else:
            arbitrage_logger.warning(f"{self.pair_name} - Missing liquidity data for {asset}, skipping liquidity check.")

        final_buy_price = weighted_buy_price if weighted_buy_price is not None else effective_buy_ex1
        final_sell_price = weighted_sell_price if weighted_sell_price is not None else effective_sell_ex2
        final_profit = ((final_sell_price - final_buy_price) / final_buy_price) * 100

        if liq_ex1 and liq_ex2 and weighted_buy_price is not None and weighted_sell_price is not None:
            # Przeliczamy zamawianą ilość na podstawie ceny z order booka
            desired_qty = investment / weighted_buy_price
            total_qty = 0
            total_cost = 0
            level_details = []
            for price, vol in breakdown_buy:
                if total_qty + vol >= desired_qty:
                    qty_from_level = desired_qty - total_qty
                    total_cost += qty_from_level * price
                    level_details.append((price, qty_from_level))
                    total_qty = desired_qty
                    break
                else:
                    total_cost += vol * price
                    level_details.append((price, vol))
                    total_qty += vol
            final_invested = total_cost
            final_proceeds = desired_qty * weighted_sell_price
            final_profit_amount = final_proceeds - final_invested
            final_profit_percent = (final_profit_amount / final_invested * 100) if final_invested else 0
        else:
            final_invested = investment
            final_proceeds = investment * (final_sell_price / final_buy_price)
            final_profit_amount = final_proceeds - final_invested
            final_profit_percent = final_profit

        try:
            log_line = (
                f"Pair: {self.pair_name} | Asset: {asset} | "
                f"Buy ({names[0]} eff.): {effective_buy_ex1:.4f} | Sell ({names[1]} eff.): {effective_sell_ex2:.4f} | "
                f"Ticker Profit: {profit1:.2f}% | Weighted Profit: {final_profit_percent:.2f}% | "
                f"Profit ({quote}): {final_profit_amount:.6f} | Invested ({quote}): {final_invested:.6f} | "
                f"Qty Purchased: {desired_qty:.4f} | Liquidity Info: "
                f"{liq_ex1.get('asks', [])[:3]} / {liq_ex2.get('bids', [])[:3]} | "
                f"Buy Levels: {breakdown_buy} | Sell Levels: {breakdown_sell}"
            )
        except Exception as format_e:
            arbitrage_logger.error(f"{self.pair_name} - Formatting error: {format_e}")
            return

        if final_profit_amount > 0:
            opp_logger.info(log_line)
        else:
            unprofitable_logger.info(log_line)

        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(
                f"{self.pair_name} - Opportunity: Buy on {self.exchange1.__class__.__name__} (price: {tickers[names[0]]}, eff.: {effective_buy_ex1:.4f}) | "
                f"Sell on {self.exchange2.__class__.__name__} (price: {tickers[names[1]]}, eff.: {effective_sell_ex2:.4f}) | "
                f"Ticker Profit: {profit1:.2f}% | Weighted Profit: {final_profit_percent:.2f}% | Profit: {final_profit_amount:.6f} {quote}"
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

if __name__ == '__main__':
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
