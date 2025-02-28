import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate

# Ustawienie loggerów (możesz korzystać z RotatingFileHandler – tutaj wykorzystujemy już skonfigurowane loggery)
arbitrage_logger = logging.getLogger("arbitrage")
opp_logger = logging.getLogger("arbitrage_opportunities")
unprofitable_logger = logging.getLogger("unprofitable_opportunities")
absurd_logger = logging.getLogger("absurd_opportunities")

def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# Asynchroniczny rate limiter – wykorzystujący asyncio.sleep()
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

# Funkcja pomocnicza do obliczenia ważonej średniej ceny przy realizacji zamówienia
def compute_weighted_average_price(levels, desired_qty):
    total_cost = 0
    total_qty = 0
    breakdown = []
    qty_remaining = desired_qty
    for price, vol in levels:
        if qty_remaining <= 0:
            break
        qty_taken = min(vol, qty_remaining)
        total_cost += price * qty_taken
        total_qty += qty_taken
        breakdown.append((price, qty_taken))
        qty_remaining -= qty_taken
    if total_qty == 0:
        return None, breakdown
    weighted_price = total_cost / total_qty
    return weighted_price, breakdown

# Pobieranie order booka – z opcjonalnym ograniczeniem liczby poziomów (ustalanym w CONFIG)
async def get_liquidity_info_async(exchange, symbol, levels_limit=None):
    try:
        order_book = await exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        if levels_limit is not None:
            bids = bids[:levels_limit]
            asks = asks[:levels_limit]
        return {"bids": bids, "asks": asks}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

# Funkcja konwersji inwestycji z USDT na jednostki quote (np. BTC)
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
        # Jeśli asset nie jest słownikiem, zakładamy, że zawiera już '/' – inaczej pomijamy.
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

        # Jeśli żaden z profity tickerowych nie spełnia progu, przerywamy dalsze obliczenia
        if profit1 < CONFIG["ARBITRAGE_THRESHOLD"] and profit2 < CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(f"{self.pair_name} - Ticker profit below threshold for asset {asset} (profit1: {profit1:.2f}%, profit2: {profit2:.2f}%), skipping further calculations.")
            return

        try:
            quote = symbol_ex1.split("/")[1]
        except Exception as e:
            arbitrage_logger.error(f"{self.pair_name} - Error determining quote from symbol {symbol_ex1}: {e}")
            return

        base_investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        investment = base_investment
        if CONFIG.get("CONVERT_INVESTMENT", {}).get(quote, False):
            from exchanges.binance import BinanceExchange  # używamy Binance jako exchange konwersyjny
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for quote {quote}: {base_investment} USDT -> {investment:.6f} {quote}")

        # Pobieramy wielopoziomowe dane order booka (ograniczone do LEVELS_LIMIT poziomów, ustawionych w config)
        levels_limit = CONFIG.get("ORDERBOOK_LEVELS", 5)
        liq_ex1 = await get_liquidity_info_async(self.exchange1, symbol_ex1, levels_limit)
        liq_ex2 = await get_liquidity_info_async(self.exchange2, symbol_ex2, levels_limit)
        liquidity_info = ""
        if liq_ex1 and 'asks' in liq_ex1:
            liquidity_info += f"{names[0]} Asks: {liq_ex1['asks']}; "
        if liq_ex2 and 'bids' in liq_ex2:
            liquidity_info += f"{names[1]} Bids: {liq_ex2['bids']}"
        
        profit_liq = None
        invested_amount = None
        actual_qty = None
        extra_info = ""
        # Jeśli mamy dane z order booków, wykonujemy obliczenia wielopoziomowe
        if liq_ex1 and liq_ex2:
            # Dla strony kupna: wykorzystujemy listę asks
            asks = liq_ex1.get('asks', [])
            # Dla strony sprzedaży: wykorzystujemy listę bids
            bids = liq_ex2.get('bids', [])
            # Ustalamy "desired_qty" na podstawie inwestycji i efektywnej ceny kupna z tickerów (używając efektywnej ceny z poziomu 1)
            effective_order_buy_level1 = liq_ex1['asks'][0][0] * (1 + fee1 / 100)
            desired_qty = investment / effective_order_buy_level1
            # Obliczamy weighted average price dla kupna (dla wymaganej ilości)
            weighted_buy_price, breakdown_buy = compute_weighted_average_price(asks, desired_qty)
            weighted_sell_price, breakdown_sell = compute_weighted_average_price(bids, desired_qty)
            if weighted_buy_price is None or weighted_sell_price is None:
                extra_info = "Insufficient liquidity levels."
            else:
                effective_order_buy = weighted_buy_price * (1 + fee1 / 100)
                effective_order_sell = weighted_sell_price * (1 - fee2 / 100)
                # Przyjmujemy, że faktycznie można zrealizować całe zamówienie, jeśli łączny wolumen jest wystarczający:
                total_buy_vol = sum([vol for _, vol in asks])
                total_sell_vol = sum([vol for _, vol in bids])
                actual_qty = min(desired_qty, total_buy_vol, total_sell_vol)
                potential_proceeds = actual_qty * effective_order_sell
                invested_amount = actual_qty * effective_order_buy
                profit_liq = potential_proceeds - invested_amount
                profit_liq_percent = (profit_liq / invested_amount * 100) if invested_amount else 0
                extra_info += f"Breakdown Buy: {breakdown_buy}; Breakdown Sell: {breakdown_sell}; "
        else:
            extra_info = "No liquidity data available."

        try:
            log_line = (
                f"Pair: {self.pair_name} | Asset: {asset} | "
                f"Buy ({names[0]} eff.): {effective_buy_ex1:.4f} | Sell ({names[1]} eff.): {effective_sell_ex2:.4f} | "
                f"Ticker Profit: {profit1:.2f}% | Weighted Profit: {f'{profit_liq_percent:.2f}' if 'profit_liq_percent' in locals() and profit_liq_percent is not None else 'N/A'}% | "
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

if __name__ == '__main__':
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
