import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate

# ----------------------
# Konfiguracja loggerów z RotatingFileHandler
from logging.handlers import RotatingFileHandler

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

# ----------------------
def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# Asynchroniczny rate limiter – działający przy użyciu asyncio.sleep()
class RateLimiter:
    def __init__(self, delay):
        self.delay = delay  # minimalny odstęp między zapytaniami (sekundy)
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

async def get_liquidity_info_async(exchange, symbol):
    try:
        order_book = await exchange.fetch_order_book(symbol)
        # Zwracamy całą listę, aby móc agregować kilka poziomów
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        return {"bids": bids, "asks": asks}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

# Funkcje pomocnicze do obliczania średniej ceny wykonania na podstawie kilku poziomów order booka

def calculate_execution_for_buy(asks, investment, fee_rate):
    """Oblicza, ile jednostek można kupić za podaną inwestycję oraz średnią cenę wykonania.
       Dla stron kupna (asks) – ceny rosnące."""
    total_cost = 0.0
    total_qty = 0.0
    for price, volume in asks:
        effective_price = price * (1 + fee_rate/100)
        level_cost = effective_price * volume
        if total_cost + level_cost >= investment:
            remaining = investment - total_cost
            qty_needed = remaining / effective_price
            total_qty += qty_needed
            total_cost += qty_needed * effective_price
            break
        else:
            total_cost += level_cost
            total_qty += volume
    if total_qty == 0:
        return None, 0
    avg_price = total_cost / total_qty
    return avg_price, total_qty

def calculate_execution_for_sell(bids, qty, fee_rate):
    """Oblicza średnią cenę wykonania dla sprzedaży określonej ilości jednostek.
       Dla stron sprzedaży (bids) – ceny malejące."""
    total_revenue = 0.0
    total_qty = 0.0
    for price, volume in bids:
        effective_price = price * (1 - fee_rate/100)
        if total_qty + volume >= qty:
            remaining = qty - total_qty
            total_revenue += remaining * effective_price
            total_qty = qty
            break
        else:
            total_revenue += volume * effective_price
            total_qty += volume
    if total_qty == 0:
        return None, 0
    avg_price = total_revenue / total_qty
    return avg_price, total_qty

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

        # Szybkie sprawdzenie tickerów do filtrowania okazji
        try:
            ticker1 = await fetch_ticker_rate_limited_async(self.exchange1, symbol_ex1)
            ticker2 = await fetch_ticker_rate_limited_async(self.exchange2, symbol_ex2)
        except asyncio.CancelledError:
            return

        tickers = {}
        if ticker1 and ticker1.get('last') is not None:
            tickers[names[0]] = ticker1.get('last')
            arbitrage_logger.info(f"{self.pair_name} - Ticker {names[0]}: {tickers[names[0]]}")
        else:
            arbitrage_logger.warning(f"{self.pair_name} - Missing ticker price for {names[0]}, skipping {asset}")
        if ticker2 and ticker2.get('last') is not None:
            tickers[names[1]] = ticker2.get('last')
            arbitrage_logger.info(f"{self.pair_name} - Ticker {names[1]}: {tickers[names[1]]}")
        else:
            arbitrage_logger.warning(f"{self.pair_name} - Missing ticker price for {names[1]}, skipping {asset}")

        if names[0] not in tickers or names[1] not in tickers:
            arbitrage_logger.warning(f"{self.pair_name} - Insufficient ticker data for {asset}, skipping.")
            return

        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        # Wstępne obliczenia na podstawie tickerów (do filtrowania)
        effective_buy_ticker = tickers[names[0]] * (1 + fee1 / 100)
        effective_sell_ticker = tickers[names[1]] * (1 - fee2 / 100)
        ticker_profit = ((effective_sell_ticker - effective_buy_ticker) / effective_buy_ticker) * 100

        # Ustalanie quote – zakładamy format "XYZ/QUOTE"
        try:
            quote = symbol_ex1.split("/")[1]
        except Exception as e:
            arbitrage_logger.error(f"{self.pair_name} - Error determining quote from {symbol_ex1}: {e}")
            return

        base_investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        investment = base_investment
        if CONFIG.get("CONVERT_INVESTMENT", {}).get(quote, False):
            from exchanges.binance import BinanceExchange  # exchange referencyjny do konwersji
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for {quote}: {base_investment} USDT -> {investment:.6f} {quote}")
        else:
            arbitrage_logger.info(f"Using base investment for {quote}: {investment} USDT")

        # Pobieramy pełne order booki dla obu symboli
        liq_ex1 = await get_liquidity_info_async(self.exchange1, symbol_ex1)
        liq_ex2 = await get_liquidity_info_async(self.exchange2, symbol_ex2)
        if not liq_ex1 or not liq_ex2:
            arbitrage_logger.warning(f"{self.pair_name} - Missing liquidity data for {asset}, skipping.")
            return

        # Dla kupna – agregujemy kilka poziomów z asks; dla sprzedaży – kilka poziomów z bids
        avg_buy_price, qty_buy_available = calculate_execution_for_buy(liq_ex1['asks'], investment, fee1)
        if avg_buy_price is None:
            arbitrage_logger.warning(f"{self.pair_name} - Could not calculate execution for buy for {asset}, skipping.")
            return

        # Zakładamy, że chcemy sprzedać tyle samo jednostek, ile możemy kupić
        avg_sell_price, qty_sell_available = calculate_execution_for_sell(liq_ex2['bids'], qty_buy_available, fee2)
        if avg_sell_price is None:
            arbitrage_logger.warning(f"{self.pair_name} - Could not calculate execution for sell for {asset}, skipping.")
            return

        # Kalkulujemy finalne wartości na podstawie order booka
        invested_amount = qty_buy_available * avg_buy_price
        potential_proceeds = qty_buy_available * avg_sell_price
        profit_orderbook = potential_proceeds - invested_amount
        profit_orderbook_percent = (profit_orderbook / invested_amount * 100) if invested_amount else 0

        extra_info = (f"Qty: {qty_buy_available:.4f}; Invested: {invested_amount:.6f} {quote}; "
                      f"Proceeds: {potential_proceeds:.6f} {quote}; ")

        # Przygotowanie loga – informacje końcowe
        log_line = (
            f"Pair: {self.pair_name} | Asset: {asset} | "
            f"Buy Price (order book eff.): {avg_buy_price:.4f} | Sell Price (order book eff.): {avg_sell_price:.4f} | "
            f"Ticker Profit: {ticker_profit:.2f}% | Orderbook Profit: {profit_orderbook_percent:.2f}% | "
            f"Profit ({quote}): {profit_orderbook:.6f} | Invested ({quote}): {invested_amount:.6f} | "
            f"Qty Purchased: {qty_buy_available:.4f} | Extra: {extra_info}"
        )

        if profit_orderbook > 0:
            opp_logger.info(log_line)
        else:
            unprofitable_logger.info(log_line)

        arbitrage_logger.info(
            f"{self.pair_name} - Opportunity: Buy on {self.exchange1.__class__.__name__} at {avg_buy_price:.4f} {quote} | "
            f"Sell on {self.exchange2.__class__.__name__} at {avg_sell_price:.4f} {quote} | "
            f"Orderbook Profit: {profit_orderbook_percent:.2f}% ({profit_orderbook:.6f} {quote})"
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

# Dodatkowe funkcje pomocnicze do obliczeń z order booka
def calculate_execution_for_buy(asks, investment, fee_rate):
    total_cost = 0.0
    total_qty = 0.0
    for price, volume in asks:
        effective_price = price * (1 + fee_rate / 100)
        level_cost = effective_price * volume
        if total_cost + level_cost >= investment:
            remaining = investment - total_cost
            qty_at_level = remaining / effective_price
            total_qty += qty_at_level
            total_cost += qty_at_level * effective_price
            break
        else:
            total_cost += level_cost
            total_qty += volume
    if total_qty == 0:
        return None, 0
    avg_price = total_cost / total_qty
    return avg_price, total_qty

def calculate_execution_for_sell(bids, required_qty, fee_rate):
    total_revenue = 0.0
    total_qty = 0.0
    for price, volume in bids:
        effective_price = price * (1 - fee_rate / 100)
        if total_qty + volume >= required_qty:
            remaining = required_qty - total_qty
            total_revenue += remaining * effective_price
            total_qty = required_qty
            break
        else:
            total_revenue += volume * effective_price
            total_qty += volume
    if total_qty == 0:
        return None, 0
    avg_price = total_revenue / total_qty
    return avg_price, total_qty

if __name__ == '__main__':
    # For testing purposes – normally the strategy is launched via common_assets
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
