import asyncio
import logging
import time
from config import CONFIG
from functools import partial
from utils import calculate_effective_buy, calculate_effective_sell

# Set up loggers
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

arbitrage_logger = logging.getLogger("arbitrage")
if not arbitrage_logger.hasHandlers():
    handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    arbitrage_logger.addHandler(handler)
    arbitrage_logger.setLevel(logging.INFO)

opp_logger = logging.getLogger("arbitrage_opportunities")
if not opp_logger.hasHandlers():
    opp_handler = logging.FileHandler("arbitrage_opportunities.log", mode="a", encoding="utf-8")
    opp_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    opp_handler.setFormatter(opp_formatter)
    opp_logger.addHandler(opp_handler)
    opp_logger.setLevel(logging.INFO)

unprofitable_logger = logging.getLogger("unprofitable_opportunities")
if not unprofitable_logger.hasHandlers():
    unprofitable_handler = logging.FileHandler("unprofitable_opportunities.log", mode="a", encoding="utf-8")
    unprofitable_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    unprofitable_handler.setFormatter(unprofitable_formatter)
    unprofitable_logger.addHandler(unprofitable_handler)
    unprofitable_logger.setLevel(logging.INFO)

absurd_logger = logging.getLogger("absurd_opportunities")
if not absurd_logger.hasHandlers():
    absurd_handler = logging.FileHandler("absurd_opportunities.log", mode="a", encoding="utf-8")
    absurd_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    absurd_handler.setFormatter(absurd_formatter)
    absurd_logger.addHandler(absurd_handler)
    absurd_logger.setLevel(logging.INFO)

def normalize_symbol(symbol):
    if ":" in symbol:
        return symbol.split(":")[0]
    return symbol

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        self.assets = assets  # dict mapping base token to dict mapping exchange to symbol
        self.pair_name = pair_name

    async def check_opportunity(self, asset):
        names = self.pair_name.split("-")
        if not isinstance(asset, dict):
            base = asset
            asset = {names[0]: base + "/USDT", names[1]: base + "/USDT"}
        symbol_ex1 = asset.get(names[0])
        symbol_ex2 = asset.get(names[1])
        if not symbol_ex1 or not symbol_ex2:
            arbitrage_logger.warning(f"{self.pair_name} - Missing full symbols for asset {asset}. Skipping.")
            return
        if symbol_ex1 == "USDT/USDT" or symbol_ex2 == "USDT/USDT":
            arbitrage_logger.warning(f"{self.pair_name} - Invalid symbol {asset} (USDT/USDT). Skipping.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Checking arbitrage for: {symbol_ex1} ({names[0]}), {symbol_ex2} ({names[1]})")
        loop = asyncio.get_running_loop()
        ticker_task1 = asyncio.create_task(self.exchange1.fetch_ticker(symbol_ex1))
        ticker_task2 = asyncio.create_task(self.exchange2.fetch_ticker(symbol_ex2))
        results = await asyncio.gather(ticker_task1, ticker_task2, return_exceptions=True)
        tickers = {}
        for key, result in zip([names[0], names[1]], results):
            if isinstance(result, Exception):
                arbitrage_logger.error(f"{self.pair_name} - Error fetching data for {key}: {result}")
            elif result:
                price = result.get('last')
                if price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - For {key} fetched price is None, skipping asset {asset}")
                else:
                    tickers[key] = price
                    arbitrage_logger.info(f"{self.pair_name} - {key}: fetched price = {price}")
        if names[0] not in tickers or names[1] not in tickers:
            arbitrage_logger.warning(f"{self.pair_name} - Insufficient ticker data for {asset}. Skipping.")
            return

        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        effective_buy_ex1 = calculate_effective_buy(tickers[names[0]], fee1)
        effective_sell_ex2 = calculate_effective_sell(tickers[names[1]], fee2)
        ticker_profit = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = calculate_effective_buy(tickers[names[1]], fee2)
        effective_sell_ex1 = calculate_effective_sell(tickers[names[0]], fee1)
        ticker_profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        liquidity_info = "N/A"
        extra_info = ""
        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        qty = None
        profit_liq_usdt = None
        profit_liq_percent = None
        invested_amount = None

        if (ticker_profit >= CONFIG["ARBITRAGE_THRESHOLD"]) or (ticker_profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            order_book_task1 = asyncio.create_task(self.exchange1.fetch_order_book(symbol_ex1))
            order_book_task2 = asyncio.create_task(self.exchange2.fetch_order_book(symbol_ex2))
            order_books = await asyncio.gather(order_book_task1, order_book_task2, return_exceptions=True)
            liq_ex1, liq_ex2 = None, None
            if not isinstance(order_books[0], Exception):
                liq_ex1 = order_books[0]
            if not isinstance(order_books[1], Exception):
                liq_ex2 = order_books[1]
            liquidity_info = ""
            if liq_ex1 and liq_ex1.get('bids') and liq_ex1.get('asks'):
                liquidity_info += f"{names[0]} - Top Bid: {liq_ex1['bids'][0]}, Top Ask: {liq_ex1['asks'][0]}; "
            if liq_ex2 and liq_ex2.get('bids') and liq_ex2.get('asks'):
                liquidity_info += f"{names[1]} - Top Bid: {liq_ex2['bids'][0]}, Top Ask: {liq_ex2['asks'][0]}"
            if liq_ex1 and liq_ex2 and liq_ex1.get('asks') and liq_ex2.get('bids'):
                top_ask_ex1 = liq_ex1['asks'][0][0]
                available_buy_vol = liq_ex1['asks'][0][1]
                top_bid_ex2 = liq_ex2['bids'][0][0]
                available_sell_vol = liq_ex2['bids'][0][1]
                effective_order_buy = calculate_effective_buy(top_ask_ex1, fee1)
                desired_qty = investment / effective_order_buy
                actual_qty = min(desired_qty, available_buy_vol, available_sell_vol)
                effective_order_sell = calculate_effective_sell(top_bid_ex2, fee2)
                potential_proceeds = actual_qty * effective_order_sell
                invested_amount = actual_qty * effective_order_buy
                profit_liq_usdt = potential_proceeds - invested_amount
                profit_liq_percent = (profit_liq_usdt / invested_amount * 100) if invested_amount else 0
                extra_info += f"Can buy {actual_qty:.4f} units; Invested: {invested_amount:.2f} USDT; Potential proceeds: {potential_proceeds:.2f} USDT; Liquidity Profit: {profit_liq_percent:.2f}% ({profit_liq_usdt:.2f} USDT)."
        else:
            extra_info = "No liquidity check as ticker profit below threshold."

        # Format log message (without using tabulate)
        log_message = (
            f"{self.pair_name} | Asset: {asset} | Buy ({names[0]}): {effective_buy_ex1:.4f} | "
            f"Sell ({names[1]}): {effective_sell_ex2:.4f} | Invested: {invested_amount:.2f if invested_amount is not None else 'N/A'} USDT | "
            f"Ticker Profit: {ticker_profit:.2f}% | Liquidity Profit: {profit_liq_percent:.2f if profit_liq_percent is not None else 'N/A'}% | "
            f"Profit (USDT): {profit_liq_usdt:.2f if profit_liq_usdt is not None else 'N/A'} | "
            f"Qty Purchased: {actual_qty:.4f if 'actual_qty' in locals() else 'N/A'} | "
            f"Liquidity Info: {liquidity_info} | Extra: {extra_info}"
        )
        # Log profitable opportunities separately from unprofitable ones
        if profit_liq_usdt is not None and profit_liq_usdt > 0:
            opp_logger.info(log_message)
        else:
            unprofitable_logger.info(log_message)

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
