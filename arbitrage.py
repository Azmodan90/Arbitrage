import asyncio
import logging
import json
import time
from logging.handlers import RotatingFileHandler
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate

# === Konfiguracja loggerów z RotatingFileHandler ===
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

# Ustawienie loggerów – wszystkie logi będą teraz rejestrowane zgodnie z naszym podziałem
arbitrage_logger = setup_logger("arbitrage", "arbitrage.log")
opp_logger = setup_logger("arbitrage_opportunities", "arbitrage_opportunities.log")
# Zrezygnowaliśmy z unprofitable_logger – wszystkie obliczenia trafiają do arbitrage_logger lub opp_logger

# === Funkcja pomocnicza do normalizacji symbolu ===
def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# === Asynchroniczny rate limiter oparty o asyncio.sleep() ===
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
        # Ograniczamy do określonej liczby poziomów, jeśli ustawione w config
        levels_to_use = CONFIG.get("ORDERBOOK_LEVELS", None)
        if levels_to_use is not None:
            order_book['asks'] = order_book.get('asks', [])[:levels_to_use]
            order_book['bids'] = order_book.get('bids', [])[:levels_to_use]
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        top_bid = bids[0] if bids else [None, None]
        top_ask = asks[0] if asks else [None, None]
        return {"top_bid": top_bid, "top_ask": top_ask, "full_order_book": order_book}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

async def convert_investment(quote, investment_usdt, conversion_exchange):
    pair = f"{quote}/USDT"
    ticker = await conversion_exchange.fetch_ticker(pair)
    if ticker is None or ticker.get("last") is None:
        return investment_usdt  # Jeśli nie uda się pobrać kursu, zwróć wartość bez konwersji
    price = ticker.get("last")
    return investment_usdt / price

def compute_weighted_average_price(order_book, desired, side):
    """
    Oblicza ważoną średnią cenę na podstawie kolejnych poziomów order booka.
    Jeśli pierwszy poziom wystarcza (wolumen >= desired), zwraca cenę z tego poziomu.
    W przeciwnym razie iteruje po poziomach i oblicza ważoną średnią.
    Zwraca (weighted_avg, breakdown) gdzie breakdown to lista (price, qty_used).
    """
    levels = order_book.get('asks', []) if side=='buy' else order_book.get('bids', [])
    if not levels:
        return None, []
    total_cost = 0.0
    total_qty = 0.0
    breakdown = []
    for price, qty in levels:
        if side == 'buy':
            # Sprawdzamy, czy na bieżącym poziomie można kupić cały desired
            if qty >= desired - total_qty:
                qty_used = desired - total_qty
                total_cost += qty_used * price
                total_qty += qty_used
                breakdown.append((price, qty_used))
                break
            else:
                total_cost += qty * price
                total_qty += qty
                breakdown.append((price, qty))
        else:  # selling – desired oznacza ilość aktywów do sprzedaży
            if qty >= desired - total_qty:
                qty_used = desired - total_qty
                total_qty += qty_used
                breakdown.append((price, qty_used))
                break
            else:
                total_qty += qty
                breakdown.append((price, qty))
    if total_qty == 0:
        return None, []
    weighted_avg = total_cost / total_qty if side=='buy' else sum(p*q for p,q in breakdown) / total_qty
    return weighted_avg, breakdown

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        self.assets = assets  # Słownik z pełnymi symbolami, np.: { "ABC/USDT": {"binance": "ABC/USDT", "bitget": "ABC/USDT"} }
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
        
        # Pobierz tickery dla obu kierunków
        ticker1 = await fetch_ticker_rate_limited_async(self.exchange1, symbol_ex1)
        ticker2 = await fetch_ticker_rate_limited_async(self.exchange2, symbol_ex2)
        if ticker1 is None or ticker2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Missing ticker data for {asset}, skipping.")
            return
        price1 = ticker1.get('last')
        price2 = ticker2.get('last')
        if price1 is None or price2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Ticker price is None for {asset}, skipping.")
            return

        # Oblicz profit w obu kierunkach
        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        effective_buy_A = price1 * (1 + fee1 / 100)
        effective_sell_A = price2 * (1 - fee2 / 100)
        profit_A = ((effective_sell_A - effective_buy_A) / effective_buy_A) * 100

        effective_buy_B = price2 * (1 + fee2 / 100)
        effective_sell_B = price1 * (1 - fee1 / 100)
        profit_B = ((effective_sell_B - effective_buy_B) / effective_buy_B) * 100

        arbitrage_logger.info(f"{self.pair_name} - Ticker Profit: Direction A: {profit_A:.2f}%, Direction B: {profit_B:.2f}%")

        # Wybieramy kierunek, który ma dodatni profit przekraczający próg
        if profit_A >= CONFIG["ARBITRAGE_THRESHOLD"] and profit_A >= profit_B:
            chosen_profit = profit_A
            chosen_symbol_buy = symbol_ex1
            chosen_symbol_sell = symbol_ex2
            chosen_exchange_buy = self.exchange1
            chosen_exchange_sell = self.exchange2
        elif profit_B >= CONFIG["ARBITRAGE_THRESHOLD"] and profit_B > profit_A:
            chosen_profit = profit_B
            chosen_symbol_buy = symbol_ex2
            chosen_symbol_sell = symbol_ex1
            chosen_exchange_buy = self.exchange2
            chosen_exchange_sell = self.exchange1
        else:
            arbitrage_logger.info(f"{self.pair_name} - No profitable ticker opportunity for asset {asset}, skipping.")
            return

        try:
            quote = chosen_symbol_buy.split("/")[1]
        except Exception as e:
            arbitrage_logger.error(f"{self.pair_name} - Error determining quote from symbol {chosen_symbol_buy}: {e}")
            return

        base_investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        investment = base_investment
        if CONFIG.get("CONVERT_INVESTMENT", {}).get(quote, False):
            from exchanges.binance import BinanceExchange  # używamy Binance jako exchange konwersyjny
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for quote {quote}: {base_investment} USDT -> {investment:.6f} {quote}")

        # Analiza order booka – wielopoziomowa, z opcją użycia tylko pierwszego poziomu, jeśli wystarcza
        liquidity_info = "N/D"
        extra_info = ""
        profit_liq = None
        invested_amount = None
        actual_qty = None
        if chosen_profit >= CONFIG["ARBITRAGE_THRESHOLD"]:
            ob_buy = await chosen_exchange_buy.fetch_order_book(chosen_symbol_buy)
            ob_sell = await chosen_exchange_sell.fetch_order_book(chosen_symbol_sell)
            levels_to_use = CONFIG.get("ORDERBOOK_LEVELS", 5)
            ob_buy['asks'] = ob_buy.get('asks', [])[:levels_to_use]
            ob_sell['bids'] = ob_sell.get('bids', [])[:levels_to_use]
            
            # Sprawdź, czy pierwszy poziom wystarczy – jeśli tak, użyj go; w przeciwnym razie oblicz ważoną średnią
            first_ask_qty = ob_buy.get('asks', [[None, 0]])[0][1]
            first_bid_qty = ob_sell.get('bids', [[None, 0]])[0][1]
            if first_ask_qty >= (investment / (ob_buy['asks'][0][0] * (1 + fee1 / 100))):
                effective_buy_final = ob_buy['asks'][0][0] * (1 + fee1 / 100)
                breakdown_buy = [(ob_buy['asks'][0][0], investment / (ob_buy['asks'][0][0] * (1 + fee1 / 100)))]
            else:
                effective_buy_final, breakdown_buy = compute_weighted_average_price(ob_buy, investment, 'buy')
            if first_bid_qty >= (investment / (ob_sell['bids'][0][0] * (1 - fee2 / 100))):
                effective_sell_final = ob_sell['bids'][0][0] * (1 - fee2 / 100)
                breakdown_sell = [(ob_sell['bids'][0][0], investment / (ob_sell['bids'][0][0] * (1 - fee2 / 100)))]
            else:
                effective_sell_final, breakdown_sell = compute_weighted_average_price(ob_sell, investment, 'sell')
            
            liquidity_info = f"Buy Levels: {breakdown_buy}; Sell Levels: {breakdown_sell}"
            profit_liq = ((effective_sell_final - effective_buy_final) / effective_buy_final) * 100
            actual_qty = investment / effective_buy_final
            invested_amount = actual_qty * effective_buy_final
            potential_proceeds = actual_qty * effective_sell_final
            extra_info += f"Qty: {actual_qty:.4f}; Invested: {invested_amount:.6f} {quote}; Proceeds: {potential_proceeds:.6f} {quote}; "
        else:
            extra_info = "No liquidity check (threshold not met)."

        try:
            final_profit = potential_proceeds - invested_amount if invested_amount is not None else None
            log_line = (
                f"Pair: {self.pair_name} | Asset: {asset} | "
                f"Buy ({chosen_exchange_buy.__class__.__name__} eff.): {effective_buy_final:.4f} | "
                f"Sell ({chosen_exchange_sell.__class__.__name__} eff.): {effective_sell_final:.4f} | "
                f"Ticker Profit: {chosen_profit:.2f}% | Liquidity Profit: {f'{profit_liq:.2f}' if profit_liq is not None else 'N/A'}% | "
                f"Profit ({quote}): {f'{final_profit:.6f}' if final_profit is not None else 'N/A'} | "
                f"Invested ({quote}): {f'{invested_amount:.6f}' if invested_amount is not None else 'N/A'} | "
                f"Qty Purchased: {f'{actual_qty:.4f}' if actual_qty is not None else 'N/A'} | "
                f"Liquidity Info: {liquidity_info} | Extra: {extra_info}"
            )
        except Exception as format_e:
            arbitrage_logger.error(f"{self.pair_name} - Formatting error: {format_e}")
            return

        opp_logger.info(log_line)
        arbitrage_logger.info(
            f"{self.pair_name} - Opportunity: Buy on {chosen_exchange_buy.__class__.__name__} (price: {price1 if chosen_exchange_buy==self.exchange1 else price2}, eff.: {effective_buy_final:.4f}) | "
            f"Sell on {chosen_exchange_sell.__class__.__name__} (price: {price2 if chosen_exchange_sell==self.exchange2 else price1}, eff.: {effective_sell_final:.4f}) | "
            f"Ticker Profit: {chosen_profit:.2f}% | Profit: {f'{final_profit:.6f}' if final_profit is not None else 'N/A'} {quote}"
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
            raise

if __name__ == '__main__':
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
