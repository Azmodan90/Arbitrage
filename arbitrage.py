import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell

# Konfiguracja loggerów
arbitrage_logger = logging.getLogger("arbitrage")
if not arbitrage_logger.hasHandlers():
    handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    arbitrage_logger.addHandler(handler)
    arbitrage_logger.setLevel(logging.INFO)
    arbitrage_logger.propagate = False

opp_logger = logging.getLogger("arbitrage_opportunities")
if not opp_logger.hasHandlers():
    opp_handler = logging.FileHandler("arbitrage_opportunities.log", mode="a", encoding="utf-8")
    opp_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    opp_handler.setFormatter(opp_formatter)
    opp_logger.addHandler(opp_handler)
    opp_logger.setLevel(logging.INFO)
    opp_logger.propagate = False

unprofitable_logger = logging.getLogger("unprofitable_opportunities")
if not unprofitable_logger.hasHandlers():
    unprofitable_handler = logging.FileHandler("unprofitable_opportunities.log", mode="a", encoding="utf-8")
    unprofitable_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    unprofitable_handler.setFormatter(unprofitable_formatter)
    unprofitable_logger.addHandler(unprofitable_handler)
    unprofitable_logger.setLevel(logging.INFO)
    unprofitable_logger.propagate = False

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

# --- Rate limiter (synchronizacja przy użyciu run_in_executor) ---
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
        # Zakładamy, że exchange posiada asynchroniczną metodę fetch_order_book (wywoływaną synchronnie przez run_in_executor)
        order_book = exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        top_bid = bids[0] if bids else [None, None]
        top_ask = asks[0] if asks else [None, None]
        return {"top_bid": top_bid, "top_ask": top_ask}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} on {exchange.__class__.__name__}: {e}")
        return None

# Funkcja konwersji inwestycji – dla par, gdzie quote wymaga przeliczenia (np. BTC)
async def convert_investment(quote, investment_usdt, conversion_exchange):
    """
    Dla podanego quote (np. BTC) pobiera kurs pary (quote/USDT) z wybranego exchange (np. Binance)
    i przelicza inwestycję z USDT na jednostki quote.
    Zakładamy, że na danej giełdzie pary są w formacie np. "BTC/USDT", gdzie cena jest wyrażona w USDT za 1 BTC.
    """
    pair = f"{quote}/USDT"
    ticker = await conversion_exchange.fetch_ticker(pair)
    if ticker is None or ticker.get("last") is None:
        return investment_usdt  # Jeśli nie uda się pobrać kursu, zwróć wartość bez konwersji
    price = ticker.get("last")
    # Aby przeliczyć USDT na quote, dzielimy inwestycję przez cenę (np. 100 USDT / 20000 USDT/BTC = 0.005 BTC)
    return investment_usdt / price

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        # assets – słownik z pełnymi symbolami, np. { "AAVE/BTC": {"binance": "AAVE/BTC", "bitget": "AAVE/BTC"} }
        self.assets = assets
        self.pair_name = pair_name  # np. "binance-bitget"

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        # Jeśli asset nie jest dict-em, zakładamy, że zawiera już '/' i stosujemy go dla obu giełd
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
        loop = asyncio.get_running_loop()
        task1 = loop.run_in_executor(None, lambda: fetch_ticker_rate_limited_sync(self.exchange1, symbol_ex1))
        task2 = loop.run_in_executor(None, lambda: fetch_ticker_rate_limited_sync(self.exchange2, symbol_ex2))
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        tickers = {}
        for key, result in zip([names[0], names[1]], results):
            if isinstance(result, Exception):
                arbitrage_logger.error(f"{self.pair_name} - Error fetching ticker for {key}: {result}")
            elif result:
                price = result.get('last')
                if price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - Ticker price for {key} is None, skipping asset {asset}")
                else:
                    tickers[key] = price
                    arbitrage_logger.info(f"{self.pair_name} - Ticker {key}: {price}")
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

        # Sprawdzenie order book tylko, gdy osiągnięto próg arbitrażu
        liquidity_info = "N/D"
        extra_info = ""
        base_investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        # Ustal quote – zakładamy, że symbol ma format "XYZ/QUOTE"
        quote = symbol_ex1.split("/")[1]
        investment = base_investment
        # Jeśli dla danego quote ustawiono konwersję, przelicz inwestycję z USDT na quote
        if CONFIG.get("CONVERT_INVESTMENT", {}).get(quote, False):
            # Dla konwersji użyjemy BinanceExchange jako exchange referencyjnego (możesz zmienić według potrzeb)
            from exchanges.binance import BinanceExchange
            conversion_exchange = BinanceExchange()
            investment = await convert_investment(quote, base_investment, conversion_exchange)
            # Zamykamy exchange konwersyjny
            await conversion_exchange.close()
            arbitrage_logger.info(f"Converted investment for quote {quote}: {base_investment} USDT -> {investment:.6f} {quote}")

        profit_liq_usdt = None
        profit_liq_percent = None
        invested_amount = None
        actual_qty = None
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            liq_ex1 = await loop.run_in_executor(None, lambda: get_liquidity_info(self.exchange1, symbol_ex1))
            liq_ex2 = await loop.run_in_executor(None, lambda: get_liquidity_info(self.exchange2, symbol_ex2))
            liquidity_info = ""
            if liq_ex1:
                liquidity_info += f"{names[0]} Top Ask: {liq_ex1['top_ask']}; "
            if liq_ex2:
                liquidity_info += f"{names[1]} Top Bid: {liq_ex2['top_bid']}"
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
                extra_info += f"Qty: {actual_qty:.4f}; Invested: {invested_amount:.6f} {quote}; Proceeds: {potential_proceeds:.6f} {quote}; "
                if available_buy_vol < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[0]} (available: {available_buy_vol}); "
                if available_sell_vol < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[1]} (available: {available_sell_vol}); "
        else:
            extra_info = "No liquidity check (threshold not met)."

        log_line = (
            f"Pair: {self.pair_name} | Asset: {asset} | "
            f"Buy ({names[0]} eff.): {effective_buy_ex1:.4f} | Sell ({names[1]} eff.): {effective_sell_ex2:.4f} | "
            f"Ticker Profit: {profit1:.2f}% | Liquidity Profit: {profit_liq_percent:.2f if profit_liq_percent is not None else 'N/A'}% | "
            f"Profit ({quote}): {profit_liq_usdt:.6f if profit_liq_usdt is not None else 'N/A'} | "
            f"Invested ({quote}): {invested_amount:.6f if invested_amount is not None else 'N/A'} | "
            f"Qty Purchased: {actual_qty:.4f if actual_qty is not None else 'N/A'} | "
            f"Liquidity Info: {liquidity_info} | Extra: {extra_info}"
        )

        # Logowanie – opłacalne okazje oddzielnie od nieopłacalnych
        if profit_liq_usdt is not None and profit_liq_usdt > 0:
            opp_logger.info(log_line)
        else:
            unprofitable_logger.info(log_line)

        # Dodatkowe tradycyjne logowanie
        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(
                f"{self.pair_name} - Opportunity: Buy on {self.exchange1.__class__.__name__} (price: {tickers[names[0]]}, eff.: {effective_buy_ex1:.4f}) | "
                f"Sell on {self.exchange2.__class__.__name__} (price: {tickers[names[1]]}, eff.: {effective_sell_ex2:.4f}) | "
                f"Ticker Profit: {profit1:.2f}% | Profit: {profit_liq_usdt:.6f} {quote}"
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
            raise

if __name__ == '__main__':
    # Dla testów (uruchomienie strategii bez assetów – normalnie używamy common_assets)
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
