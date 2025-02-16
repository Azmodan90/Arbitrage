import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
import logger_config

# Ustawienie centralne logowania
logger_config.setup_logging()

# Pobieramy dedykowane loggery
arbitrage_logger = logging.getLogger("arbitrage")
opp_logger = logging.getLogger("arbitrage_opportunities")
unprofitable_logger = logging.getLogger("unprofitable_opportunities")
absurd_logger = logging.getLogger("absurd_opportunities")

# --- Rate limiter (synchronous implementation) ---
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

# Asynchroniczna wersja pobierania order book
async def get_liquidity_info_async(exchange, symbol):
    try:
        order_book = await exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        top_bid = bids[0] if bids else [None, None]
        top_ask = asks[0] if asks else [None, None]
        return {"top_bid": top_bid, "top_ask": top_ask}
    except Exception as e:
        arbitrage_logger.error(
            f"Błąd pobierania order book dla {symbol} na {exchange.__class__.__name__}: {e}"
        )
        return None

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        # assets – słownik mapujący pełne symbole, np.:
        # { "ABC/USDT": {"binance": "ABC/USDT", "bitget": "ABC/USDT"} }
        self.assets = assets
        self.pair_name = pair_name

    async def check_opportunity(self, asset):
        """
        Sprawdza okazję arbitrażową i loguje wynik.
        Dla opłacalnych okazji loguje:
          - Pair: para giełd
          - Symbol: symbol (pojedynczy, przyjmujemy że obie giełdy używają tego samego symbolu)
          - Buy Price: cena zakupu (z opłatą)
          - Sell Price: cena sprzedaży (z opłatą)
          - Profit: profit w %
          - Invested: kwota zainwestowana
        Dla nieopłacalnych okazji loguje:
          - Pair, Symbol oraz informację, dlaczego okazja była nieopłacalna.
        """
        names = self.pair_name.split("-")
        if not isinstance(asset, dict):
            if "/" in asset:
                asset = {names[0]: asset, names[1]: asset}
            else:
                arbitrage_logger.error(f"{self.pair_name} - Asset '{asset}' nie zawiera '/', pomijam.")
                return

        # Przyjmujemy, że symbol jest taki sam dla obu giełd
        symbol = asset.get(names[0])
        symbol2 = asset.get(names[1])
        if not symbol or not symbol2:
            arbitrage_logger.warning(f"{self.pair_name} - Brak pełnych danych symbolu dla asset {asset}. Pomijam.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam arbitraż dla symbolu: {symbol}")

        # Pobieramy tickery asynchronicznie
        task1 = fetch_ticker_rate_limited_async(self.exchange1, symbol)
        task2 = fetch_ticker_rate_limited_async(self.exchange2, symbol2)
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        tickers = {}
        for key, result in zip([names[0], names[1]], results):
            if isinstance(result, Exception):
                arbitrage_logger.error(f"{self.pair_name} - Błąd pobierania ticker dla {key}: {result}")
            elif result:
                price = result.get('last')
                if price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - Cena ticker dla {key} jest None, pomijam asset {asset}")
                else:
                    tickers[key] = price
        if names[0] not in tickers or names[1] not in tickers:
            arbitrage_logger.warning(f"{self.pair_name} - Niedostateczne dane ticker dla {asset}. Pomijam.")
            return

        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        # Obliczamy efektywne ceny z opłatami
        effective_buy_ex1 = tickers[names[0]] * (1 + fee1 / 100)
        effective_sell_ex2 = tickers[names[1]] * (1 - fee2 / 100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = tickers[names[1]] * (1 + fee2 / 100)
        effective_sell_ex1 = tickers[names[0]] * (1 - fee1 / 100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        invested_amount = None

        # Pobieramy dane płynności, jeśli profit przekracza próg
        extra_info = ""
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            liq_ex1 = await get_liquidity_info_async(self.exchange1, symbol)
            liq_ex2 = await get_liquidity_info_async(self.exchange2, symbol2)
            if liq_ex1 and liq_ex2:
                top_ask_ex1 = liq_ex1['top_ask'][0]
                available_buy_vol = liq_ex1['top_ask'][1]
                top_bid_ex2 = liq_ex2['top_bid'][0]
                available_sell_vol = liq_ex2['top_bid'][1]
                effective_order_buy = top_ask_ex1 * (1 + fee1 / 100)
                desired_qty = investment / effective_order_buy
                qty = min(desired_qty, available_buy_vol, available_sell_vol)
                effective_order_sell = top_bid_ex2 * (1 - fee2 / 100)
                potential_proceeds = qty * effective_order_sell
                invested_amount = qty * effective_order_buy
            else:
                extra_info = "Brak wystarczających danych płynności."
        else:
            extra_info = "Profit poniżej progu arbitrażu."

        # Logowanie - wybieramy opłacalną lub nieopłacalną okazję
        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (
                f"Pair: {self.pair_name} | Symbol: {symbol} | "
                f"Buy Price: {effective_buy_ex1:.4f} | Sell Price: {effective_sell_ex2:.4f} | "
                f"Profit: {profit1:.2f}% | Invested: {invested_amount if invested_amount is not None else 'N/A'}"
            )
            opp_logger.info(msg)
        elif profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (
                f"Pair: {self.pair_name} | Symbol: {symbol} | "
                f"Buy Price: {effective_buy_ex2:.4f} | Sell Price: {effective_sell_ex1:.4f} | "
                f"Profit: {profit2:.2f}% | Invested: {invested_amount if invested_amount is not None else 'N/A'}"
            )
            opp_logger.info(msg)
        else:
            msg = (
                f"Pair: {self.pair_name} | Symbol: {symbol} | "
                f"Unprofitable: {extra_info}"
            )
            unprofitable_logger.info(msg)

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
    import asyncio
    from config import CONFIG
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
