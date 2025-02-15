import asyncio
import logging
import json
import time
from config import CONFIG
from utils import calculate_effective_buy, calculate_effective_sell
from tabulate import tabulate

# Konfiguracja loggerów (arbitrage, opp, unprofitable, absurd) – jak w Twoim kodzie
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
    return symbol.split(":")[0] if ":" in symbol else symbol

# Używamy asynchronicznych funkcji giełdowych – zakładamy, że klasy giełdowe zostały zaktualizowane
async def get_ticker(exchange, symbol):
    try:
        ticker = await exchange.fetch_ticker(symbol)
        return ticker
    except Exception as e:
        arbitrage_logger.error(f"Error fetching ticker from {exchange.__class__.__name__} for {symbol}: {e}")
        return None

async def get_liquidity_info(exchange, symbol):
    try:
        order_book = await exchange.exchange.fetch_order_book(symbol)
        bids = order_book.get('bids', [])
        asks = order_book.get('asks', [])
        top_bid = bids[0] if bids else [None, None]
        top_ask = asks[0] if asks else [None, None]
        return {"top_bid": top_bid, "top_ask": top_ask}
    except Exception as e:
        arbitrage_logger.error(f"Error fetching order book for {symbol} from {exchange.__class__.__name__}: {e}")
        return None

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        self.assets = assets  # słownik mapujący np.: {"GMT": {"binance": "GMT/USDT", "kucoin": "GMT/USDT"}}
        self.pair_name = pair_name

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        if not isinstance(asset, dict):
            base = asset
            asset = {names[0]: base + "/USDT", names[1]: base + "/USDT"}
        symbol_ex1 = asset.get(names[0])
        symbol_ex2 = asset.get(names[1])
        if not symbol_ex1 or not symbol_ex2 or symbol_ex1 == "USDT/USDT" or symbol_ex2 == "USDT/USDT":
            arbitrage_logger.warning(f"{self.pair_name} - Invalid or missing symbols for asset {asset}. Skipping.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Checking arbitrage for: {symbol_ex1} ({names[0]}), {symbol_ex2} ({names[1]})")
        ticker1 = await get_ticker(self.exchange1, symbol_ex1)
        ticker2 = await get_ticker(self.exchange2, symbol_ex2)
        if ticker1 is None or ticker2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Insufficient ticker data for {asset}. Skipping.")
            return
        price1, price2 = ticker1.get('last'), ticker2.get('last')
        if price1 is None or price2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Ticker price missing for {asset}. Skipping.")
            return

        fee1, fee2 = self.exchange1.fee_rate, self.exchange2.fee_rate
        effective_buy_ex1 = price1 * (1 + fee1 / 100)
        effective_sell_ex2 = price2 * (1 - fee2 / 100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = price2 * (1 + fee2 / 100)
        effective_sell_ex1 = price1 * (1 - fee1 / 100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        # Sprawdzenie order book dla doprecyzowania kwoty inwestycji
        liquidity_info = "N/D"
        extra_info = ""
        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        profit_liq_usdt = None
        profit_liq_percent = None
        invested_amount = None
        actual_qty = None
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            liq_ex1 = await get_liquidity_info(self.exchange1, symbol_ex1)
            liq_ex2 = await get_liquidity_info(self.exchange2, symbol_ex2)
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
                extra_info += f"Qty: {actual_qty:.4f}; Invested: {invested_amount:.2f} USDT; Proceeds: {potential_proceeds:.2f} USDT; "
                if available_buy_vol < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[0]} (avail: {available_buy_vol}); "
                if available_sell_vol < desired_qty:
                    extra_info += f"Insufficient liquidity on {names[1]} (avail: {available_sell_vol}); "
        else:
            extra_info = "No liquidity check (below threshold)."

        headers = ["Pair", "Asset", "Buy Ex", "Buy Price", "Sell Ex", "Sell Price", "Ticker Profit (%)", 
                   "Liquidity Profit (%)", "Profit (USDT)", "Invested (USDT)", "Qty", "Liquidity Info"]
        row = [
            self.pair_name,
            asset,
            names[0],
            f"{effective_buy_ex1:.4f}",
            names[1],
            f"{effective_sell_ex2:.4f}",
            f"{profit1:.2f}",
            f"{profit_liq_percent:.2f}" if profit_liq_percent is not None else "N/A",
            f"{profit_liq_usdt:.2f}" if profit_liq_usdt is not None else "N/A",
            f"{invested_amount:.2f}" if invested_amount is not None else "N/A",
            f"{actual_qty:.4f}" if actual_qty is not None else "N/A",
            liquidity_info
        ]
        table_str = tabulate([row], headers=headers, tablefmt="pipe")
        if profit_liq_usdt is not None and profit_liq_usdt > 0:
            opp_logger.info(table_str)
        else:
            unprofitable_logger.info(table_str)

        # Dodatkowe tradycyjne logowanie
        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} - Opportunity: Buy on {self.exchange1.__class__.__name__} (ticker: {price1}, effective: {effective_buy_ex1:.4f}) "
                   f"and sell on {self.exchange2.__class__.__name__} (ticker: {price2}, effective: {effective_sell_ex2:.4f}), "
                   f"Ticker Profit: {profit1:.2f}% [Liquidity: {liquidity_info} | {extra_info}]")
            arbitrage_logger.info(msg)
        if profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} - Opportunity: Buy on {self.exchange2.__class__.__name__} (ticker: {price2}, effective: {effective_buy_ex2:.4f}) "
                   f"and sell on {self.exchange1.__class__.__name__} (ticker: {price1}, effective: {effective_sell_ex1:.4f}), "
                   f"Ticker Profit: {profit2:.2f}% [Liquidity: {liquidity_info} | {extra_info}]")
            arbitrage_logger.info(msg)

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
    pass
