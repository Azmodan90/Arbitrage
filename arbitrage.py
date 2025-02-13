import asyncio
import logging
import time
from config import CONFIG
from utils import calculate_effective_buy, calculate_effective_sell

# Ustawienia loggerów (jak wcześniej)
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

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        # assets – słownik mapujący token bazowy do mapowania symboli, np.
        # { "GMT": { "binance": "GMT/USDT", "kucoin": "GMT/USDT" } }
        self.assets = assets
        self.pair_name = pair_name

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        if not isinstance(asset, dict):
            base = asset
            asset = { names[0]: base + "/USDT", names[1]: base + "/USDT" }
        
        symbol_ex1 = asset.get(names[0])
        symbol_ex2 = asset.get(names[1])
        if not symbol_ex1 or not symbol_ex2:
            arbitrage_logger.warning(f"{self.pair_name} - Brak pełnych symboli dla asset {asset}. Pomijam.")
            return

        if symbol_ex1 == "USDT/USDT" or symbol_ex2 == "USDT/USDT":
            arbitrage_logger.warning(f"{self.pair_name} - Nieprawidłowy symbol {asset} (USDT/USDT). Pomijam.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam okazje arbitrażowe dla symboli: {symbol_ex1} (dla {names[0]}), {symbol_ex2} (dla {names[1]})")
        # Pobieranie tickerów asynchronicznie
        task1 = asyncio.create_task(self.exchange1.fetch_ticker(symbol_ex1))
        task2 = asyncio.create_task(self.exchange2.fetch_ticker(symbol_ex2))
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

        # Pobieramy order book tylko gdy okazja przekracza próg
        liquidity_info = "N/D"
        extra_info = ""
        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            liq_ex1 = await self.exchange1.fetch_order_book(symbol_ex1)
            liq_ex2 = await self.exchange2.fetch_order_book(symbol_ex2)
            liquidity_info = ""
            if liq_ex1 and liq_ex1.get('asks'):
                liquidity_info += f"{names[0]} - Top Ask: {liq_ex1['asks'][0]}; "
            if liq_ex2 and liq_ex2.get('bids'):
                liquidity_info += f"{names[1]} - Top Bid: {liq_ex2['bids'][0]}"
            if liq_ex1 and liq_ex2 and liq_ex1.get('asks') and liq_ex2.get('bids'):
                top_ask_ex1 = liq_ex1['asks'][0][0]
                available_buy_vol = liq_ex1['asks'][0][1]
                top_bid_ex2 = liq_ex2['bids'][0][0]
                available_sell_vol = liq_ex2['bids'][0][1]
                effective_order_buy = top_ask_ex1 * (1 + fee1 / 100)
                desired_qty = investment / effective_order_buy
                actual_qty = min(desired_qty, available_buy_vol, available_sell_vol)
                extra_info += f"Można kupić {actual_qty:.4f} jednostek; "
                if available_buy_vol < desired_qty:
                    extra_info += f"Niewystarczająca płynność na {names[0]} (dostępne: {available_buy_vol}); "
                if available_sell_vol < desired_qty:
                    extra_info += f"Niewystarczająca płynność na {names[1]} (dostępne: {available_sell_vol}); "
                effective_order_sell = top_bid_ex2 * (1 - fee2 / 100)
                potential_proceeds = actual_qty * effective_order_sell
                extra_info += f"Potencjalne przychody: {potential_proceeds:.2f} USDT; "
                # Dodatkowo logujemy nową kwotę zainwestowaną – to jest ilość faktycznie zakupionych aktywów razy cena kupna (effective_order_buy)
                adjusted_investment = actual_qty * effective_order_buy
                extra_info += f"Zainwestowano: {adjusted_investment:.2f} USDT."
        else:
            extra_info = "Brak sprawdzania płynności, gdy okazja nie przekracza progu."

        # Logujemy wyniki – oddzielnie dla obu wariantów (kupno na exchange1 i exchange2)
        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} | {asset} | {self.exchange1.__class__.__name__} | {tickers[names[0]]:.4f} | "
                   f"{self.exchange2.__class__.__name__} | {tickers[names[1]]:.4f} | {profit1:.2f}% | {investment} USDT | "
                   f"[Liquidity -> {liquidity_info} | {extra_info}]")
            arbitrage_logger.info(msg)
            opp_logger.info(msg)
        if profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} | {asset} | {self.exchange2.__class__.__name__} | {tickers[names[1]]:.4f} | "
                   f"{self.exchange1.__class__.__name__} | {tickers[names[0]]:.4f} | {profit2:.2f}% | {investment} USDT | "
                   f"[Liquidity -> {liquidity_info} | {extra_info}]")
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
