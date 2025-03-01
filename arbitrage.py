import asyncio
import logging
import json
import time
from logging.handlers import RotatingFileHandler
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate

# === Konfiguracja loggerów przy użyciu RotatingFileHandler ===

def setup_logger(logger_name, log_file, level=logging.INFO):
    logger = logging.getLogger(logger_name)
    if not logger.hasHandlers():
        handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger

# Logger ogólny – logi działania programu (mogą być też używane w main.py)
app_logger = setup_logger("app", "app.log", level=logging.INFO)
# Logger do obliczeń – wszystkie obliczenia arbitrażu (wcześniej unprofitable.log był osobno, teraz wszystko trafia tutaj)
arbitrage_logger = setup_logger("arbitrage", "arbitrage.log", level=logging.INFO)
# Logger dla okazji opłacalnych (tylko te, które spełniają próg)
opp_logger = setup_logger("arbitrage_opportunities", "arbitrage_opportunities.log", level=logging.INFO)

# === Inne funkcje pomocnicze ===

def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# Asynchroniczny rate limiter – działa przy użyciu asyncio.sleep()
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
        # Tutaj można ograniczyć listę do pierwszych N poziomów (N definiujemy w CONFIG, np. CONFIG["ORDERBOOK_LEVELS"])
        levels = CONFIG.get("ORDERBOOK_LEVELS")
        bids = order_book.get('bids', [])[:levels]
        asks = order_book.get('asks', [])[:levels]
        top_bid = bids[0] if bids else [None, None]
        top_ask = asks[0] if asks else [None, None]
        return {"bids": bids, "asks": asks, "top_bid": top_bid, "top_ask": top_ask}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

async def convert_investment(quote, investment_usdt, conversion_exchange):
    pair = f"{quote}/USDT"
    ticker = await conversion_exchange.fetch_ticker(pair)
    if ticker is None or ticker.get("last") is None:
        return investment_usdt  # jeśli nie uda się pobrać kursu, zwróć wartość bez konwersji
    price = ticker.get("last")
    return investment_usdt / price

# Funkcja pomocnicza do obliczenia ważonej średniej ceny dla wielu poziomów orderbooka
def compute_weighted_average_price(levels):
    total_qty = sum(qty for price, qty in levels)
    if total_qty == 0:
        return 0
    weighted_sum = sum(price * qty for price, qty in levels)
    return weighted_sum / total_qty

# === Klasa strategii arbitrażu ===

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

        # Najpierw pobieramy tickery
        try:
            ticker1 = await fetch_ticker_rate_limited_async(self.exchange1, symbol_ex1)
            ticker2 = await fetch_ticker_rate_limited_async(self.exchange2, symbol_ex2)
        except asyncio.CancelledError:
            return

        tickers = {}
        if ticker1 and ticker1.get('last') is not None:
            tickers[names[0]] = ticker1.get('last')
            arbitrage_logger.info(f"{self.pair_name} - Ticker {names[0]}: {tickers[names[0]]}")
        if ticker2 and ticker2.get('last') is not None:
            tickers[names[1]] = ticker2.get('last')
            arbitrage_logger.info(f"{self.pair_name} - Ticker {names[1]}: {tickers[names[1]]}")
        if names[0] not in tickers or names[1] not in tickers:
            arbitrage_logger.warning(f"{self.pair_name} - Insufficient ticker data for {asset}, skipping.")
            return

        # Obliczenia profitów z tickerów (obliczane w obu kierunkach)
        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        effective_buy_ex1 = tickers[names[0]] * (1 + fee1 / 100)
        effective_sell_ex2 = tickers[names[1]] * (1 - fee2 / 100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = tickers[names[1]] * (1 + fee2 / 100)
        effective_sell_ex1 = tickers[names[0]] * (1 - fee1 / 100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        # Jeżeli żadna ze strategii nie przekracza progu, pomijamy dalsze obliczenia
        if profit1 < CONFIG["ARBITRAGE_THRESHOLD"] and profit2 < CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(f"{self.pair_name} - Ticker profits ({profit1:.2f}%, {profit2:.2f}%) below threshold, skipping order book check.")
            return

        # Pobieramy order book (ograniczony do określonej liczby poziomów)
        liq_ex1 = await get_liquidity_info_async(self.exchange1, symbol_ex1)
        liq_ex2 = await get_liquidity_info_async(self.exchange2, symbol_ex2)
        if liq_ex1 is None or liq_ex2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Missing liquidity data for {asset}, skipping.")
            return

        # Ustalanie quote – zakładamy format "XYZ/QUOTE"
        try:
            quote = symbol_ex1.split("/")[1]
        except Exception as e:
            arbitrage_logger.error(f"{self.pair_name} - Error determining quote from symbol {symbol_ex1}: {e}")
            return

        base_investment = CONFIG.get("INVESTMENT_AMOUNT")
        investment = base_investment
        if CONFIG.get("CONVERT_INVESTMENT", {}).get(quote, False):
            from exchanges.binance import BinanceExchange  # używamy Binance jako exchange konwersyjny
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for quote {quote}: {base_investment} USDT -> {investment:.6f} {quote}")

        # Wielopoziomowe przetwarzanie order booka
        # Najpierw sprawdzamy, czy poziom 1 jest wystarczający
        available_buy = sum(qty for price, qty in liq_ex1["asks"])
        available_sell = sum(qty for price, qty in liq_ex2["bids"])
        # Jeśli suma z poziomów 1 jest wystarczająca, możemy użyć tylko pierwszego poziomu
        # W przeciwnym razie liczymy ważoną średnią dla kolejnych poziomów
        levels_used_buy = liq_ex1["asks"]
        levels_used_sell = liq_ex2["bids"]

        # Obliczamy ważoną średnią cenę kupna i sprzedaży
        weighted_buy = compute_weighted_average_price(levels_used_buy)
        weighted_sell = compute_weighted_average_price(levels_used_sell)

        # Finalne obliczenia – używamy cen z order booka
        effective_order_buy = weighted_buy * (1 + fee1 / 100)
        effective_order_sell = weighted_sell * (1 - fee2 / 100)
        desired_qty = investment / effective_order_buy
        # Zakładamy, że chcemy kupić (i sprzedać) tyle, ile wynosi 'desired_qty', ale możemy ograniczyć do dostępnych wolumenów
        qty_possible = min(desired_qty, available_buy, available_sell)
        potential_proceeds = qty_possible * effective_order_sell
        invested_amount = qty_possible * effective_order_buy
        profit_liq = potential_proceeds - invested_amount
        profit_liq_percent = (profit_liq / invested_amount * 100) if invested_amount else 0

        extra_info = f"Weighted Buy Price: {weighted_buy:.6f}, Weighted Sell Price: {weighted_sell:.6f}; Levels Buy: {liq_ex1['asks']}; Levels Sell: {liq_ex2['bids']}"
        log_line = (
            f"Pair: {self.pair_name} | Asset: {asset} | "
            f"Buy ({names[0]} eff.): {effective_order_buy:.4f} | Sell ({names[1]} eff.): {effective_order_sell:.4f} | "
            f"Ticker Profit: {profit1:.2f}% | Liquidity Profit: {profit_liq_percent:.2f}% | "
            f"Profit ({quote}): {profit_liq:.6f} | Invested ({quote}): {invested_amount:.6f} | "
            f"Qty Purchased: {qty_possible:.4f} | Extra: {extra_info}"
        )

        # Logujemy wszystko do arbitrage_logger (wszystkie obliczenia) 
        arbitrage_logger.info(log_line)
        # Jeśli wynik finalny jest opłacalny, logujemy to osobno w opp_logger
        if profit_liq > 0:
            opp_logger.info(log_line)

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
