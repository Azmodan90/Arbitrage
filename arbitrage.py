import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell

# Ustawienie loggerów

# Logger ogólny – zapis do arbitrage.log
arbitrage_logger = logging.getLogger("arbitrage")
if not arbitrage_logger.hasHandlers():
    handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    arbitrage_logger.addHandler(handler)
    arbitrage_logger.setLevel(logging.INFO)
    arbitrage_logger.propagate = False

# Logger okazji opłacalnych – zapis do arbitrage_opportunities.log
opp_logger = logging.getLogger("arbitrage_opportunities")
if not opp_logger.hasHandlers():
    opp_handler = logging.FileHandler("arbitrage_opportunities.log", mode="a", encoding="utf-8")
    opp_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    opp_handler.setFormatter(opp_formatter)
    opp_logger.addHandler(opp_handler)
    opp_logger.setLevel(logging.INFO)
    opp_logger.propagate = False

# Logger nieopłacalnych okazji – zapis do unprofitable_opportunities.log
unprofitable_logger = logging.getLogger("unprofitable_opportunities")
if not unprofitable_logger.hasHandlers():
    unprofitable_handler = logging.FileHandler("unprofitable_opportunities.log", mode="a", encoding="utf-8")
    unprofitable_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    unprofitable_handler.setFormatter(unprofitable_formatter)
    unprofitable_logger.addHandler(unprofitable_handler)
    unprofitable_logger.setLevel(logging.INFO)
    unprofitable_logger.propagate = False

# Logger absurdalnych okazji – zapis do absurd_opportunities.log
absurd_logger = logging.getLogger("absurd_opportunities")
if not absurd_logger.hasHandlers():
    absurd_handler = logging.FileHandler("absurd_opportunities.log", mode="a", encoding="utf-8")
    absurd_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    absurd_handler.setFormatter(absurd_formatter)
    absurd_logger.addHandler(absurd_handler)
    absurd_logger.setLevel(logging.INFO)
    absurd_logger.propagate = False

def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

def get_quote_from_symbol(symbol):
    parts = symbol.split("/")
    if len(parts) == 2:
        return parts[1]
    return None

def is_quote_allowed(exchange_name, symbol):
    # Pobierz dozwolone quote dla danej giełdy z configu; domyślnie ["USDT"]
    allowed = CONFIG.get(f"{exchange_name.upper()}_ALLOWED_QUOTES", ["USDT"])
    quote = get_quote_from_symbol(symbol)
    return quote in allowed

# --- Prosty rate limiter ---
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
        # assets – lista elementów; każdy element powinien być słownikiem np.:
        # { "binance": "ABC/USDT", "kucoin": "ABC/USDT" } lub już przygotowany string, który wtedy zostanie przekonwertowany
        self.assets = assets
        self.pair_name = pair_name  # np. "binance-kucoin (USDT)" lub "binance-kucoin (EUR)"
    
    async def check_opportunity(self, asset):
        # Rozdziel nazwy giełd oraz pobierz quote z pary (zakładamy format "binance-kucoin (QUOTE)")
        base_pair = self.pair_name.split("(")[0].strip()  # np. "binance-kucoin"
        names = base_pair.split("-")
        quote = "USDT"
        if "(" in self.pair_name and ")" in self.pair_name:
            quote = self.pair_name.split("(")[-1].split(")")[0].strip()
        
        # Jeśli asset nie jest słownikiem, konwertujemy go
        if not isinstance(asset, dict):
            base = asset
            asset = { names[0]: base + "/" + quote, names[1]: base + "/" + quote }
        
        # Pobieramy symbole dla obu giełd
        try:
            symbol_ex1 = asset.get(names[0])
            symbol_ex2 = asset.get(names[1])
        except Exception as e:
            arbitrage_logger.error(f"{self.pair_name} - Błąd w dostępie do asset: {asset}. Exception: {e}")
            return
        
        if not symbol_ex1 or not symbol_ex2:
            arbitrage_logger.warning(f"{self.pair_name} - Brak pełnych symboli dla asset {asset}. Pomijam.")
            return
        if symbol_ex1 == "USDT/USDT" or symbol_ex2 == "USDT/USDT":
            arbitrage_logger.warning(f"{self.pair_name} - Nieprawidłowy symbol {asset} (USDT/USDT). Pomijam.")
            return
        
        # Sprawdzamy, czy dla danej giełdy symbol zawiera dozwolony quote (wg configu)
        if not is_quote_allowed(names[0], symbol_ex1):
            arbitrage_logger.warning(f"{self.pair_name} - Symbol {symbol_ex1} na {names[0]} nie zawiera dozwolonego quote. Pomijam.")
            return
        if not is_quote_allowed(names[1], symbol_ex2):
            arbitrage_logger.warning(f"{self.pair_name} - Symbol {symbol_ex2} na {names[1]} nie zawiera dozwolonego quote. Pomijam.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam okazje arbitrażowe dla symboli: {symbol_ex1} (dla {names[0]}), {symbol_ex2} (dla {names[1]})")
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

        effective_buy_ex1 = tickers[names[0]] * (1 + fee1 / 100)
        effective_sell_ex2 = tickers[names[1]] * (1 - fee2 / 100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = tickers[names[1]] * (1 + fee2 / 100)
        effective_sell_ex1 = tickers[names[0]] * (1 - fee1 / 100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        # Sprawdzamy order book tylko, gdy okazja przekracza próg arbitrażu
        liquidity_info = "N/D"
        extra_info = ""
        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        profit_liq_usdt = None
        profit_liq_percent = None
        invested_amount = None
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
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
                effective_order_sell = top_bid_ex2 * (1 - fee2 / 100)
                potential_proceeds = actual_qty * effective_order_sell
                invested_amount = actual_qty * effective_order_buy
                profit_liq_usdt = potential_proceeds - invested_amount
                profit_liq_percent = (profit_liq_usdt / invested_amount * 100) if invested_amount else 0
                extra_info += f"Można kupić {actual_qty:.4f} jednostek; "
                if available_buy_vol < desired_qty:
                    extra_info += f"Niewystarczająca płynność na {names[0]} (dostępne: {available_buy_vol}); "
                if available_sell_vol < desired_qty:
                    extra_info += f"Niewystarczająca płynność na {names[1]} (dostępne: {available_sell_vol}); "
                extra_info += f"Potencjalne przychody: {potential_proceeds:.2f} USDT;"
        else:
            extra_info = "Brak sprawdzania płynności, gdy okazja nie przekracza progu."

        # Budujemy komunikat logowania (logujemy jako zwykły tekst)
        log_message = (
            f"Pair: {self.pair_name} | Asset: {asset} | "
            f"Buy ({names[0]}): {effective_buy_ex1:.4f} | Sell ({names[1]}): {effective_sell_ex2:.4f} | "
            f"Ticker Profit: {profit1:.2f}% | Liquidity Profit: {profit_liq_percent:.2f if profit_liq_percent is not None else 'N/A'}% | "
            f"Profit (USDT): {profit_liq_usdt:.2f if profit_liq_usdt is not None else 'N/A'} | "
            f"Invested (USDT): {invested_amount:.2f if invested_amount is not None else 'N/A'} | "
            f"Qty Purchased: {actual_qty:.4f if 'actual_qty' in locals() else 'N/A'} | "
            f"Liquidity Info: {liquidity_info}"
        )

        # Rozdzielamy opłacalne i nieopłacalne okazje
        if profit_liq_usdt is not None and profit_liq_usdt > 0:
            opp_logger.info(log_message)
        else:
            unprofitable_logger.info(log_message)

        # Dodatkowe logowanie – logujemy również informacje z tickerów, jeśli okazja przekracza próg arbitrażu
        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(
                f"{self.pair_name} - Okazja arbitrażowa dla {asset}: Kupno na {self.exchange1.__class__.__name__} "
                f"(cena: {tickers[names[0]]}, efektywna: {effective_buy_ex1:.4f}), "
                f"sprzedaż na {self.exchange2.__class__.__name__} (cena: {tickers[names[1]]}, efektywna: {effective_sell_ex2:.4f}), "
                f"Ticker Profit: {profit1:.2f}% [Liquidity -> {liquidity_info} | {extra_info}]"
            )
        if profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(
                f"{self.pair_name} - Okazja arbitrażowa dla {asset}: Kupno na {self.exchange2.__class__.__name__} "
                f"(cena: {tickers[names[1]]}, efektywna: {effective_buy_ex2:.4f}), "
                f"sprzedaż na {self.exchange1.__class__.__name__} (cena: {tickers[names[0]]}, efektywna: {effective_sell_ex1:.4f}), "
                f"Ticker Profit: {profit2:.2f}% [Liquidity -> {liquidity_info} | {extra_info}]"
            )

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

if __name__ == '__main__':
    pass
