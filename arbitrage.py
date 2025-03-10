import asyncio
import logging
import json
import time
from logging.handlers import RotatingFileHandler
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell

# Używamy RotatingFileHandler do logowania – konfiguracja logerów
def setup_logger(logger_name, log_file, level=logging.INFO):
    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.propagate = False
    return logger

arbitrage_logger = setup_logger("arbitrage", "arbitrage.log")
opp_logger = setup_logger("arbitrage_opportunities", "arbitrage_opportunities.log")
# Jeśli potrzebujemy oddzielnie logować nieopłacalne okazje – można dodać oddzielny logger,
# ale zgodnie z ostatnimi ustaleniami wszystkie okazje trafiają do głównego logu.

def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# Funkcja pomocnicza do obliczania ważonej średniej ceny z kilku poziomów orderbooka
def compute_weighted_average(order_levels, desired_qty):
    total_cost = 0
    total_volume = 0
    used_levels = []
    remaining = desired_qty
    for level in order_levels:
        price, vol = level
        if remaining <= 0:
            break
        used_vol = min(vol, remaining)
        total_cost += used_vol * price
        total_volume += used_vol
        used_levels.append((price, used_vol))
        remaining -= used_vol
    if total_volume == 0:
        return None, used_levels
    weighted_avg = total_cost / total_volume
    return weighted_avg, used_levels

# Asynchroniczny rate limiter
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

async def get_liquidity_info_async(exchange, symbol, levels_to_fetch=CONFIG.get("ORDERBOOK_LEVELS", 5)):
    try:
        order_book = await exchange.fetch_order_book(symbol)
        asks = order_book.get('asks', [])[:levels_to_fetch]
        bids = order_book.get('bids', [])[:levels_to_fetch]
        return {"asks": asks, "bids": bids}
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
        self.assets = assets  # Słownik pełnych symboli, np. { "ABC/USDT": {"binance": "ABC/USDT", "bitget": "ABC/USDT"} }
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

        # Pobierz tickery asynchronicznie
        try:
            ticker1 = await fetch_ticker_rate_limited_async(self.exchange1, symbol_ex1)
            ticker2 = await fetch_ticker_rate_limited_async(self.exchange2, symbol_ex2)
        except asyncio.CancelledError:
            return

        if ticker1 is None or ticker2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Missing ticker data for {asset}, skipping.")
            return

        price1 = ticker1.get('last')
        price2 = ticker2.get('last')
        if price1 is None or price2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Ticker price is None for {asset}, skipping.")
            return

        # Oblicz zysk na podstawie cen tickerów dla obu kierunków:
        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate
        effective_buy_ex1 = price1 * (1 + fee1 / 100)
        effective_sell_ex2 = price2 * (1 - fee2 / 100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = price2 * (1 + fee2 / 100)
        effective_sell_ex1 = price1 * (1 - fee1 / 100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        threshold = CONFIG.get("ARBITRAGE_THRESHOLD", 2)
        if profit1 < threshold and profit2 < threshold:
            arbitrage_logger.info(f"{self.pair_name} - Ticker profit below threshold for {asset}, skipping further calculations.")
            return

        # Wybierz kierunek z lepszym zyskiem
        if profit1 >= threshold and profit1 >= profit2:
            chosen_direction = 1
            chosen_profit = profit1
            buy_exchange = self.exchange1
            sell_exchange = self.exchange2
            symbol_buy = symbol_ex1
            symbol_sell = symbol_ex2
        elif profit2 >= threshold:
            chosen_direction = 2
            chosen_profit = profit2
            buy_exchange = self.exchange2
            sell_exchange = self.exchange1
            symbol_buy = symbol_ex2
            symbol_sell = symbol_ex1
        else:
            arbitrage_logger.info(f"{self.pair_name} - No valid arbitrage direction for {asset}, skipping.")
            return

        try:
            quote = symbol_buy.split("/")[1]
        except Exception as e:
            arbitrage_logger.error(f"{self.pair_name} - Error determining quote from symbol {symbol_buy}: {e}")
            return

        base_investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        investment = base_investment
        if CONFIG.get("CONVERT_INVESTMENT", {}).get(quote, False):
            from exchanges.binance import BinanceExchange
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for quote {quote}: {base_investment} USDT -> {investment:.6f} {quote}")

        # Sprawdzenie płynności – używamy wielu poziomów order booka
        orderbook_data_buy = await get_liquidity_info_async(buy_exchange, symbol_buy, levels_to_fetch=CONFIG.get("ORDERBOOK_LEVELS", 5))
        orderbook_data_sell = await get_liquidity_info_async(sell_exchange, symbol_sell, levels_to_fetch=CONFIG.get("ORDERBOOK_LEVELS", 5))
        if orderbook_data_buy is None or orderbook_data_sell is None:
            arbitrage_logger.warning(f"{self.pair_name} - Missing order book data for {asset}, skipping liquidity check.")
            return

        asks = orderbook_data_buy.get("asks", [])
        bids = orderbook_data_sell.get("bids", [])

        if not asks or not bids:
            arbitrage_logger.warning(f"{self.pair_name} - Insufficient order book levels for {asset}, skipping.")
            return

        # Najpierw sprawdź, czy pierwszy poziom wystarcza
        first_ask = asks[0]
        effective_order_buy_first = first_ask[0] * (1 + fee1 / 100)
        desired_qty = investment / effective_order_buy_first
        if first_ask[1] >= desired_qty:
            weighted_buy_price = first_ask[0]
            buy_breakdown = [(first_ask[0], desired_qty)]
        else:
            weighted_buy_price, buy_breakdown = compute_weighted_average(asks, desired_qty)
            if weighted_buy_price is None:
                arbitrage_logger.warning(f"{self.pair_name} - Unable to compute weighted average buy price for {asset}, skipping.")
                return

        # Analogicznie dla sprzedaży
        first_bid = bids[0]
        effective_order_sell_first = first_bid[0] * (1 - fee2 / 100)
        desired_qty_sell = investment / effective_order_sell_first
        if first_bid[1] >= desired_qty_sell:
            weighted_sell_price = first_bid[0]
            sell_breakdown = [(first_bid[0], desired_qty_sell)]
        else:
            weighted_sell_price, sell_breakdown = compute_weighted_average(bids, desired_qty_sell)
            if weighted_sell_price is None:
                arbitrage_logger.warning(f"{self.pair_name} - Unable to compute weighted average sell price for {asset}, skipping.")
                return

        effective_buy_final = weighted_buy_price * (1 + fee1 / 100)
        effective_sell_final = weighted_sell_price * (1 - fee2 / 100)
        profit_liq = ((effective_sell_final - effective_buy_final) / effective_buy_final) * 100

        # Założenie: rzeczywista ilość to desired_qty (można też sumować breakdown, ale zakładamy, że suma breakdown = desired_qty)
        actual_qty = desired_qty  
        invested_amount = actual_qty * effective_buy_final
        potential_proceeds = actual_qty * effective_sell_final

        extra_info = f"Weighted Buy Price: {weighted_buy_price:.6f}, Weighted Sell Price: {weighted_sell_price:.6f}; "
        extra_info += f"Breakdown Buy: {buy_breakdown}; Breakdown Sell: {sell_breakdown}; "

        log_line = (
            f"Pair: {self.pair_name} | Asset: {asset} | "
            f"Buy ({buy_exchange.__class__.__name__} eff.): {effective_buy_final:.6f} | "
            f"Sell ({sell_exchange.__class__.__name__} eff.): {effective_sell_final:.6f} | "
            f"Ticker Profit: {chosen_profit:.2f}% | Liquidity Profit: {profit_liq:.2f}% | "
            f"Profit ({quote}): {potential_proceeds - invested_amount:.6f} | "
            f"Invested ({quote}): {invested_amount:.6f} | Qty Purchased: {actual_qty:.4f} | "
            f"Liquidity Info: Buy Levels: {asks}; Sell Levels: {bids} | Extra: {extra_info}"
        )

        if profit_liq is not None and profit_liq > 0:
            opp_logger.info(log_line)
        else:
            arbitrage_logger.info(log_line)

        if chosen_direction == 1 and profit1 >= threshold:
            arbitrage_logger.info(
                f"{self.pair_name} - Opportunity Direction 1: Buy on {self.exchange1.__class__.__name__} at {price1} | "
                f"Sell on {self.exchange2.__class__.__name__} at {price2} | Ticker Profit: {profit1:.2f}%"
            )
        elif chosen_direction == 2 and profit2 >= threshold:
            arbitrage_logger.info(
                f"{self.pair_name} - Opportunity Direction 2: Buy on {self.exchange2.__class__.__name__} at {price2} | "
                f"Sell on {self.exchange1.__class__.__name__} at {price1} | Ticker Profit: {profit2:.2f}%"
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
