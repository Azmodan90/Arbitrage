import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell

# Logger dla ogólnych informacji arbitrażu – zapis do pliku arbitrage.log
arbitrage_logger = logging.getLogger("arbitrage")
if not arbitrage_logger.hasHandlers():
    handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    arbitrage_logger.addHandler(handler)
    arbitrage_logger.setLevel(logging.INFO)
    arbitrage_logger.propagate = False

# Logger dla opłacalnych okazji arbitrażowych – zapis do pliku arbitrage_opportunities.log
opp_logger = logging.getLogger("arbitrage_opportunities")
if not opp_logger.hasHandlers():
    opp_handler = logging.FileHandler("arbitrage_opportunities.log", mode="a", encoding="utf-8")
    opp_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    opp_handler.setFormatter(opp_formatter)
    opp_logger.addHandler(opp_handler)
    opp_logger.setLevel(logging.INFO)
    opp_logger.propagate = False

# Logger dla nieopłacalnych okazji (ujemny zysk) – zapis do pliku non_profitable_opportunities.log
loss_logger = logging.getLogger("non_profitable_opportunities")
if not loss_logger.hasHandlers():
    loss_handler = logging.FileHandler("non_profitable_opportunities.log", mode="a", encoding="utf-8")
    loss_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    loss_handler.setFormatter(loss_formatter)
    loss_logger.addHandler(loss_handler)
    loss_logger.setLevel(logging.INFO)
    loss_logger.propagate = False

def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# --- Rate limiter (przykładowa implementacja) ---
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

def fetch_ticker_rate_limited_sync(exchange, symbol):
    now = time.monotonic()
    limiter = get_rate_limiter(exchange)
    wait_time = limiter.delay - (now - limiter.last_request)
    if wait_time > 0:
        time.sleep(wait_time)
    ticker = exchange.fetch_ticker(symbol)
    limiter.last_request = time.monotonic()
    return ticker

def get_liquidity_info(exchange, symbol):
    try:
        if hasattr(exchange, "fetch_order_book"):
            order_book = exchange.fetch_order_book(symbol)
        else:
            order_book = exchange.exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        top_bid = bids[0] if bids else [None, None]
        top_ask = asks[0] if asks else [None, None]
        return {"top_bid": top_bid, "top_ask": top_ask}
    except Exception as e:
        arbitrage_logger.error(f"Błąd pobierania order book dla {symbol} na {exchange.__class__.__name__}: {e}")
        return None

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        # assets – słownik mapujący token bazowy do mapowania symboli, np.:
        # { "GMT": { "binance": "GMT/USDT", "kucoin": "GMT/USDT" } }
        self.assets = assets
        self.pair_name = pair_name  # np. "binance-kucoin"

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        # Jeśli asset nie jest słownikiem, traktujemy go jako symbol bazowy i dodajemy "/USDT"
        if not isinstance(asset, dict):
            base = asset
            asset = {names[0]: base + "/USDT", names[1]: base + "/USDT"}
        
        symbol_ex1 = asset.get(names[0])
        symbol_ex2 = asset.get(names[1])
        if not symbol_ex1 or not symbol_ex2:
            arbitrage_logger.warning(f"{self.pair_name} - Brak pełnych symboli dla asset {asset}. Pomijam.")
            return
        if symbol_ex1 == "USDT/USDT" or symbol_ex2 == "USDT/USDT":
            arbitrage_logger.warning(f"{self.pair_name} - Nieprawidłowy symbol {asset} (USDT/USDT). Pomijam.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam okazje arbitrażowe dla symboli: {symbol_ex1} ({names[0]}), {symbol_ex2} ({names[1]})")
        loop = asyncio.get_running_loop()

        task1 = loop.run_in_executor(None, lambda: fetch_ticker_rate_limited_sync(self.exchange1, symbol_ex1))
        task2 = loop.run_in_executor(None, lambda: fetch_ticker_rate_limited_sync(self.exchange2, symbol_ex2))
        
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        tickers = {}
        for key, result in zip([names[0], names[1]], results):
            if isinstance(result, Exception):
                arbitrage_logger.error(f"{self.pair_name} - Błąd pobierania danych dla {key}: {result}")
            elif result:
                price = result.get('last')
                if price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - Dla {key} pobrana cena jest None, pomijam asset {asset}")
                else:
                    tickers[key] = price
                    arbitrage_logger.info(f"{self.pair_name} - {key}: pobrana cena = {price}")
        if names[0] not in tickers or names[1] not in tickers:
            arbitrage_logger.warning(f"{self.pair_name} - Niedostateczne dane dla {asset}. Pomijam.")
            return

        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        # Obliczenia na podstawie tickerów
        effective_buy_ex1 = tickers[names[0]] * (1 + fee1 / 100)
        effective_sell_ex2 = tickers[names[1]] * (1 - fee2 / 100)
        ticker_profit = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        # Jeśli okazja przekracza próg, pobieramy order book i sprawdzamy płynność
        liquidity_info = "N/D"
        extra_info = ""
        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        if ticker_profit >= CONFIG["ARBITRAGE_THRESHOLD"]:
            liq_ex1 = await loop.run_in_executor(None, lambda: get_liquidity_info(self.exchange1, symbol_ex1))
            liq_ex2 = await loop.run_in_executor(None, lambda: get_liquidity_info(self.exchange2, symbol_ex2))
            liquidity_info = ""
            if liq_ex1:
                liquidity_info += f"{names[0]} - Top Bid: {liq_ex1['top_bid']}, Top Ask: {liq_ex1['top_ask']}; "
            if liq_ex2:
                liquidity_info += f"{names[1]} - Top Bid: {liq_ex2['top_bid']}, Top Ask: {liq_ex2['top_ask']}"
            if liq_ex1 and liq_ex2:
                top_ask_ex1 = liq_ex1['top_ask'][0]
                available_buy_vol = liq_ex1['top_ask'][1]
                top_bid_ex2 = liq_ex2['top_bid'][0]
                available_sell_vol = liq_ex2['top_bid'][1]
                effective_order_buy = top_ask_ex1 * (1 + fee1 / 100)
                desired_qty = investment / effective_order_buy
                actual_qty = min(desired_qty, available_buy_vol, available_sell_vol)
                adjusted_investment = actual_qty * effective_order_buy
                effective_order_sell = top_bid_ex2 * (1 - fee2 / 100)
                potential_proceeds = actual_qty * effective_order_sell
                profit_USDT = potential_proceeds - adjusted_investment
                profit_percent_adjusted = (profit_USDT / adjusted_investment) * 100 if adjusted_investment > 0 else 0
                liquidity_status = "sufficient" if (available_buy_vol >= desired_qty and available_sell_vol >= desired_qty) else "insufficient"
                extra_info = (f"Ilość: {actual_qty:.4f} | Inwestycja: {adjusted_investment:.2f} USDT | "
                              f"Przychody: {potential_proceeds:.2f} USDT | Profit: {profit_USDT:.2f} USDT "
                              f"({profit_percent_adjusted:.2f}%) | Liquidity: {liquidity_status}")
            else:
                extra_info = "Nie udało się pobrać danych o płynności."
        else:
            extra_info = "Brak sprawdzania płynności, gdy okazja nie przekracza progu."

        # Budujemy komunikat logowany – format: 
        # "pair | asset | Buy: exchange, effective buy price | Sell: exchange, effective sell price | TickerProfit: % | Inwestycja: USDT | Ilość: | Przychody: USDT | Liquidity: | Profit: USDT (% adjusted)"
        log_msg = (f"{self.pair_name} | {asset} | Buy: {self.exchange1.__class__.__name__}, {effective_buy_ex1:.4f} | "
                   f"Sell: {self.exchange2.__class__.__name__}, {effective_sell_ex2:.4f} | "
                   f"TickerProfit: {ticker_profit:.2f}% | {extra_info}")
        # W zależności od ostatecznego zysku (po płynności) logujemy do oddzielnych plików
        if ticker_profit >= CONFIG["ARBITRAGE_THRESHOLD"]:
            # Jeśli ostatecznie (po dostosowaniu) profit_USDT jest dostępny, używamy go – w przeciwnym razie logujemy ticker_profit
            final_profit_USDT = profit_USDT if 'profit_USDT' in locals() else 0
            if final_profit_USDT >= 0:
                opp_logger.info(log_msg)
            else:
                loss_logger.info(log_msg)
        else:
            arbitrage_logger.info(log_msg)

    async def run(self):
        arbitrage_logger.info(f"{self.pair_name} - Uruchamiam strategię arbitrażu dla {len(self.assets)} aktywów.")
        try:
            while True:
                for asset in self.assets:
                    await self.check_opportunity(asset)
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            arbitrage_logger.info(f"{self.pair_name} - Strategia arbitrażu została anulowana.")
            raise
