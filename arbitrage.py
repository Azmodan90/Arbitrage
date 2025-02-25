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

# Funkcja pobiera order book – ograniczamy liczbę poziomów do ORDERBOOK_LEVELS z config
async def get_liquidity_info_async(exchange, symbol):
    try:
        limit = CONFIG.get("ORDERBOOK_LEVELS", 5)
        try:
            order_book = await exchange.fetch_order_book(symbol, {"limit": limit})
        except Exception:
            order_book = await exchange.fetch_order_book(symbol)
        # Wycinamy tylko pierwsze 'limit' poziomów (jeśli zwrócone są więcej)
        bids = order_book.get('bids', [])[:limit]
        asks = order_book.get('asks', [])[:limit]
        return {"bids": bids, "asks": asks}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

# Funkcja pomocnicza – oblicza ważoną średnią cenę dla określonego poziomu order booka
def calculate_weighted_price(levels, desired_qty):
    total_cost = 0.0
    total_qty = 0.0
    for price, volume in levels:
        if total_qty + volume >= desired_qty:
            needed = desired_qty - total_qty
            total_cost += price * needed
            total_qty += needed
            break
        else:
            total_cost += price * volume
            total_qty += volume
    if total_qty < desired_qty:
        return None  # Niewystarczająca płynność
    return total_cost / desired_qty

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
            from exchanges.binance import BinanceExchange  # Używamy Binance jako exchange konwersyjny
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for quote {quote}: {base_investment} USDT -> {investment:.6f} {quote}")

        profit_liq = None
        invested_amount = None
        actual_qty = None
        liquidity_info = "N/D"
        extra_info = ""
        # Sprawdzamy order book tylko, gdy profit z tickera przekracza próg
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            liq_ex1 = await get_liquidity_info_async(self.exchange1, symbol_ex1)
            liq_ex2 = await get_liquidity_info_async(self.exchange2, symbol_ex2)
            liquidity_info = ""
            if liq_ex1:
                liquidity_info += f"{names[0]} Asks: {liq_ex1['asks']}; "
            if liq_ex2:
                liquidity_info += f"{names[1]} Bids: {liq_ex2['bids']}"
            if liq_ex1 and liq_ex2:
                # Pobieramy poziomy asks i bids (ograniczone do ORDERBOOK_LEVELS)
                asks = liq_ex1.get("asks", [])
                bids = liq_ex2.get("bids", [])
                # Obliczamy żądaną ilość aktywów, bazując na cenie effective_buy_ex1
                desired_qty = investment / effective_buy_ex1
                # Jeśli wolumen w pierwszym poziomie wystarcza, używamy ceny z tego poziomu
                if asks and bids and asks[0][1] >= desired_qty and bids[0][1] >= desired_qty:
                    effective_buy_price = asks[0][0] * (1 + fee1 / 100)
                    effective_sell_price = bids[0][0] * (1 - fee2 / 100)
                    actual_qty = desired_qty
                else:
                    # W przeciwnym razie wyliczamy ważoną średnią cenę kupna i sprzedaży z dostępnych poziomów
                    effective_buy_price = calculate_weighted_price(asks, desired_qty)
                    effective_sell_price = calculate_weighted_price(bids, desired_qty)
                    actual_qty = desired_qty
                if effective_buy_price is None or effective_sell_price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - Insufficient aggregated liquidity for {asset}, skipping.")
                    return
                potential_proceeds = actual_qty * effective_sell_price
                invested_amount = actual_qty * effective_buy_price
                profit_liq = potential_proceeds - invested_amount
                profit_liq_percent = (profit_liq / invested_amount * 100) if invested_amount else 0
                extra_info += (f"Qty: {actual_qty:.4f}; Invested: {invested_amount:.6f} {quote}; "
                               f"Proceeds: {potential_proceeds:.6f} {quote}; ")
                # Dodatkowe informacje o niewystarczającej płynności
                total_ask_vol = sum(vol for price, vol in asks)
                total_bid_vol = sum(vol for price, vol in bids)
                if total_ask_vol < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[0]} (total available: {total_ask_vol}); "
                if total_bid_vol < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[1]} (total available: {total_bid_vol}); "
            else:
                extra_info = "No liquidity data available."
        else:
            extra_info = "No liquidity check (threshold not met)."

        try:
            log_line = (
                f"Pair: {self.pair_name} | Asset: {asset} | "
                f"Buy ({names[0]} eff.): {effective_buy_ex1:.4f} | Sell ({names[1]} eff.): {effective_sell_ex2:.4f} | "
                f"Ticker Profit: {profit1:.2f}% | Liquidity Profit: {f'{profit_liq_percent:.2f}' if profit_liq is not None else 'N/A'}% | "
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

# Funkcja pomocnicza calculate_weighted_price
def calculate_weighted_price(levels, desired_qty):
    total_cost = 0.0
    total_qty = 0.0
    for price, volume in levels:
        if total_qty + volume >= desired_qty:
            needed = desired_qty - total_qty
            total_cost += price * needed
            total_qty += needed
            break
        else:
            total_cost += price * volume
            total_qty += volume
    if total_qty < desired_qty:
        return None  # Insufficient liquidity
    return total_cost / desired_qty

if __name__ == '__main__':
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
