import asyncio
import logging
import json
from config import CONFIG
from functools import partial
import time

# Logger dla ogólnych informacji arbitrażu – zapis do pliku arbitrage.log
arbitrage_logger = logging.getLogger("arbitrage")
if not arbitrage_logger.hasHandlers():
    handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    arbitrage_logger.addHandler(handler)
    arbitrage_logger.setLevel(logging.INFO)
    arbitrage_logger.propagate = False

# Logger dla wykrytych okazji arbitrażowych – zapis do pliku arbitrage_opportunities.log
opp_logger = logging.getLogger("arbitrage_opportunities")
if not opp_logger.hasHandlers():
    opp_handler = logging.FileHandler("arbitrage_opportunities.log", mode="a", encoding="utf-8")
    opp_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    opp_handler.setFormatter(opp_formatter)
    opp_logger.addHandler(opp_handler)
    opp_logger.setLevel(logging.INFO)
    opp_logger.propagate = False

# Logger dla absurdalnych okazji – zapis do pliku absurd_opportunities.log
absurd_logger = logging.getLogger("absurd_opportunities")
if not absurd_logger.hasHandlers():
    absurd_handler = logging.FileHandler("absurd_opportunities.log", mode="a", encoding="utf-8")
    absurd_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    absurd_handler.setFormatter(absurd_formatter)
    absurd_logger.addHandler(absurd_handler)
    absurd_logger.setLevel(logging.INFO)
    absurd_logger.propagate = False

def normalize_symbol(symbol):
    """
    Normalizuje symbol rynkowy, usuwając dodatkowe sufiksy po znaku dwukropka.
    Przykładowo: "STPT/USDT:USDT" -> "STPT/USDT"
    """
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

# --- Rate Limiter (bez zmian) ---
class RateLimiter:
    def __init__(self, delay):
        self.delay = delay  # minimalny odstęp między zapytaniami (w sekundach)
        self.lock = asyncio.Lock()
        self.last_request = 0

    async def wait(self):
        async with self.lock:
            now = time.monotonic()
            wait_time = self.delay - (now - self.last_request)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self.last_request = time.monotonic()

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

async def fetch_ticker_rate_limited(exchange, symbol):
    """
    Asynchronicznie pobiera ticker z danego exchange, przestrzegając ograniczenia rate limitera.
    """
    limiter = get_rate_limiter(exchange)
    await limiter.wait()
    return exchange.fetch_ticker(symbol)

def get_liquidity_info(exchange, symbol):
    """
    Pobiera dane order book dla danego symbolu i zwraca informacje o top bid i top ask.
    """
    try:
        order_book = exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        top_bid = bids[0] if bids else [None, None]
        top_ask = asks[0] if asks else [None, None]
        return {"top_bid": top_bid, "top_ask": top_ask}
    except Exception as e:
        arbitrage_logger.error(f"Błąd pobierania order book dla {symbol} na {exchange.__class__.__name__}: {e}")
        return None

# --- Strategia arbitrażu ---
class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        # assets – słownik, gdzie klucz to token bazowy, a wartością jest mapowanie pełnych symboli, np.
        # { "binance": "GAME/USDT", "kucoin": "GAME/USDT" }
        self.assets = assets
        self.pair_name = pair_name  # np. "binance-kucoin"

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        # Jeśli asset nie jest słownikiem, konwertujemy go do domyślnego mapowania (dodajemy "/USDT")
        if not isinstance(asset, dict):
            base = asset
            asset = { names[0]: base + "/USDT", names[1]: base + "/USDT" }
        
        symbol_ex1 = asset.get(names[0])
        symbol_ex2 = asset.get(names[1])
        if not symbol_ex1 or not symbol_ex2:
            arbitrage_logger.warning(f"{self.pair_name} - Brak pełnych symboli dla asset {asset}. Pomijam.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam okazje arbitrażowe dla symboli: {symbol_ex1} (dla {names[0]}), {symbol_ex2} (dla {names[1]})")
        loop = asyncio.get_running_loop()

        # Pobieranie danych tickerów z uwzględnieniem rate limitera
        if hasattr(self.exchange1, 'fetch_ticker_limited'):
            task1 = asyncio.create_task(self.exchange1.fetch_ticker_limited(symbol_ex1))
        else:
            task1 = loop.run_in_executor(None, lambda: asyncio.run(fetch_ticker_rate_limited(self.exchange1, symbol_ex1)))
        
        if hasattr(self.exchange2, 'fetch_ticker_limited'):
            task2 = asyncio.create_task(self.exchange2.fetch_ticker_limited(symbol_ex2))
        else:
            task2 = loop.run_in_executor(None, lambda: asyncio.run(fetch_ticker_rate_limited(self.exchange2, symbol_ex2)))
        
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

        # Pobieramy dane o płynności z order booka dla obu giełd
        liquidity_ex1 = await loop.run_in_executor(None, lambda: get_liquidity_info(self.exchange1, symbol_ex1))
        liquidity_ex2 = await loop.run_in_executor(None, lambda: get_liquidity_info(self.exchange2, symbol_ex2))

        liquidity_info = ""
        if liquidity_ex1:
            liquidity_info += f"{names[0]} - Top Bid: {liquidity_ex1['top_bid']}, Top Ask: {liquidity_ex1['top_ask']}; "
        if liquidity_ex2:
            liquidity_info += f"{names[1]} - Top Bid: {liquidity_ex2['top_bid']}, Top Ask: {liquidity_ex2['top_ask']}"

        if profit1 > CONFIG["ABSURD_THRESHOLD"]:
            absurd_logger.warning(f"{self.pair_name} - Absurdally wysoki zysk dla {asset}: {profit1:.2f}% (Kupno na {self.exchange1.__class__.__name__}, Sprzedaż na {self.exchange2.__class__.__name__}). Ignoruję okazję. [{liquidity_info}]")
        elif profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} - Okazja arbitrażowa dla {asset}: Kupno na {self.exchange1.__class__.__name__} "
                   f"(cena: {tickers[names[0]]}, efektywna: {effective_buy_ex1:.4f}), sprzedaż na {self.exchange2.__class__.__name__} "
                   f"(cena: {tickers[names[1]]}, efektywna: {effective_sell_ex2:.4f}), zysk: {profit1:.2f}%. "
                   f"Liquidity -> {liquidity_info}")
            arbitrage_logger.info(msg)
            opp_logger.info(msg)

        if profit2 > CONFIG["ABSURD_THRESHOLD"]:
            absurd_logger.warning(f"{self.pair_name} - Absurdally wysoki zysk dla {asset}: {profit2:.2f}% (Kupno na {self.exchange2.__class__.__name__}, Sprzedaż na {self.exchange1.__class__.__name__}). Ignoruję okazję. [{liquidity_info}]")
        elif profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} - Okazja arbitrażowa dla {asset}: Kupno na {self.exchange2.__class__.__name__} "
                   f"(cena: {tickers[names[1]]}, efektywna: {effective_buy_ex2:.4f}), sprzedaż na {self.exchange1.__class__.__name__} "
                   f"(cena: {tickers[names[0]]}, efektywna: {effective_sell_ex1:.4f}), zysk: {profit2:.2f}%. "
                   f"Liquidity -> {liquidity_info}")
            arbitrage_logger.info(msg)
            opp_logger.info(msg)

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
