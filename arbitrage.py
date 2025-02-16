import asyncio
import logging
import json
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate
import ccxt.async_support as ccxt_async  # Używamy asynchronicznej wersji ccxt

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

# Rate limiter – podobnie jak wcześniej, ale dla async
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

async def fetch_ticker_rate_limited(exchange, symbol):
    key = exchange.__class__.__name__.lower()
    if key not in rate_limiters:
        delay = RATE_LIMITS.get(key, 0.1)
        rate_limiters[key] = RateLimiter(delay)
    limiter = rate_limiters[key]
    now = time.monotonic()
    wait_time = limiter.delay - (now - limiter.last_request)
    if wait_time > 0:
        await asyncio.sleep(wait_time)
    ticker = await exchange.fetch_ticker(symbol)
    limiter.last_request = time.monotonic()
    return ticker

async def get_liquidity_info(exchange, symbol):
    try:
        order_book = await exchange.fetch_order_book(symbol, params={'limit': 5})
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
        self.assets = assets  # słownik: { "BTC/USDT": { "binance": "BTC/USDT", "kucoin": "BTC/USDT" } , ... }
        self.pair_name = pair_name

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        # Jeśli asset nie jest słownikiem, używamy domyślnego quote z config
        if not isinstance(asset, dict):
            quote = CONFIG.get("QUOTE", "USDT")
            base = asset
            asset = {names[0]: base + "/" + quote, names[1]: base + "/" + quote}
        else:
            # Wyciągamy quote z pierwszego symbolu w asset (zakładamy, że na obu giełdach jest ten sam)
            example_symbol = next(iter(asset.values()))
            try:
                base, detected_quote = example_symbol.split("/")
            except Exception as e:
                arbitrage_logger.error(f"Błąd przy parsowaniu symbolu {example_symbol}: {e}")
                return
            quote = detected_quote

        symbol_ex1 = asset.get(names[0])
        symbol_ex2 = asset.get(names[1])
        if not symbol_ex1 or not symbol_ex2 or symbol_ex1 == f"{quote}/{quote}" or symbol_ex2 == f"{quote}/{quote}":
            arbitrage_logger.warning(f"{self.pair_name} - Błędny symbol {asset}. Pomijam.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam: {symbol_ex1} ({names[0]}), {symbol_ex2} ({names[1]})")
        task1 = asyncio.create_task(fetch_ticker_rate_limited(self.exchange1, symbol_ex1))
        task2 = asyncio.create_task(fetch_ticker_rate_limited(self.exchange2, symbol_ex2))
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        tickers = {}
        for key, result in zip([names[0], names[1]], results):
            if isinstance(result, Exception):
                arbitrage_logger.error(f"{self.pair_name} - Błąd dla {key}: {result}")
            elif result:
                price = result.get('last')
                if price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - Brak ceny dla {key}, pomijam {asset}")
                else:
                    tickers[key] = price
                    arbitrage_logger.info(f"{self.pair_name} - {key} cena: {price}")
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

        liquidity_info = "N/D"
        extra_info = ""
        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        qty = None
        profit_liq_usdt = None
        profit_liq_percent = None
        invested_amount = None

        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"] or profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            liq_ex1 = await get_liquidity_info(self.exchange1, symbol_ex1)
            liq_ex2 = await get_liquidity_info(self.exchange2, symbol_ex2)
            liquidity_info = ""
            if liq_ex1:
                liquidity_info += f"{names[0]} Top Bid: {liq_ex1['top_bid']}, Top Ask: {liq_ex1['top_ask']}; "
            if liq_ex2:
                liquidity_info += f"{names[1]} Top Bid: {liq_ex2['top_bid']}, Top Ask: {liq_ex2['top_ask']}"
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
                profit_liq_usdt = potential_proceeds - invested_amount
                profit_liq_percent = (profit_liq_usdt / invested_amount * 100) if invested_amount else 0
                extra_info += f"Qty: {qty:.4f}; Inwestycja: {invested_amount:.2f} USDT; Przychody: {potential_proceeds:.2f} USDT; "
                if available_buy_vol < desired_qty:
                    extra_info += f"Niewystarczająca płynność na {names[0]} (dostępne: {available_buy_vol}); "
                if available_sell_vol < desired_qty:
                    extra_info += f"Niewystarczająca płynność na {names[1]} (dostępne: {available_sell_vol}); "
                extra_info += f"Zysk: {profit_liq_percent:.2f}% / {profit_liq_usdt:.2f} USDT; "
            else:
                extra_info = "Brak sprawdzania płynności (okazja poniżej progu)."

        log_data = {
            "pair": self.pair_name,
            "asset": asset,
            "buy_exchange": names[0],
            "buy_price": f"{effective_buy_ex1:.4f}",
            "sell_exchange": names[1],
            "sell_price": f"{effective_sell_ex2:.4f}",
            "invested": f"{invested_amount:.2f}" if invested_amount is not None else "N/A",
            "profit_usdt": f"{profit_liq_usdt:.2f}" if profit_liq_usdt is not None else "N/A",
            "ticker_profit_percent": f"{profit1:.2f}",
            "liq_info": liquidity_info,
            "extra": extra_info
        }

        if profit_liq_usdt is not None and profit_liq_usdt > 0:
            opp_logger.info(" | ".join(str(x) for x in log_data.values()))
        else:
            unprofitable_logger.info(" | ".join(str(x) for x in log_data.values()))

        if profit1 > CONFIG["ABSURD_THRESHOLD"]:
            absurd_logger.warning(f"{self.pair_name} - Absurdally wysoki zysk dla {asset}: {profit1:.2f}%. Ignoruję. [Liquidity: {liquidity_info} | {extra_info}]")
        elif profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(f"{self.pair_name} - Okazja: {asset} | Kupno: {names[0]} {effective_buy_ex1:.4f} | Sprzedaż: {names[1]} {effective_sell_ex2:.4f} | Ticker zysk: {profit1:.2f}% | Inwestycja: {invested_amount if invested_amount is not None else 'N/A'} USDT | Profit: {profit_liq_usdt if profit_liq_usdt is not None else 'N/A'} USDT | {extra_info}")

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

# Przy zamykaniu pamiętaj o wywołaniu exchange.close() dla asynchronicznych instancji, jeśli używasz ccxt.async_support.
