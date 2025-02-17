import asyncio
import logging
import time
from config import CONFIG
from utils import calculate_effective_buy, calculate_effective_sell

# Logger configuration
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

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        self.assets = assets  # oczekujemy słownika np.: { "ABC/USDT": {"binance": "ABC/USDT", "bitget": "ABC/USDT"} }
        self.pair_name = pair_name

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
            arbitrage_logger.warning(f"{self.pair_name} - Incomplete symbol data for asset {asset}. Skipping.")
            return

        arbitrage_logger.info(f"{self.pair_name} - Checking arbitrage for: {symbol_ex1} ({names[0]}), {symbol_ex2} ({names[1]})")
        # Pobieramy dane tickerów asynchronicznie
        ticker1 = await self.exchange1.fetch_ticker(symbol_ex1)
        ticker2 = await self.exchange2.fetch_ticker(symbol_ex2)
        if ticker1 is None or ticker2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Missing ticker data for {asset}. Skipping.")
            return
        price1 = ticker1.get('last')
        price2 = ticker2.get('last')
        if price1 is None or price2 is None:
            arbitrage_logger.warning(f"{self.pair_name} - Ticker price is None for {asset}. Skipping.")
            return
        arbitrage_logger.info(f"{self.pair_name} - Ticker prices: {names[0]}: {price1}, {names[1]}: {price2}")

        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        effective_buy_ex1 = price1 * (1 + fee1/100)
        effective_sell_ex2 = price2 * (1 - fee2/100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = price2 * (1 + fee2/100)
        effective_sell_ex1 = price1 * (1 - fee1/100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        liquidity_info = "N/D"
        extra_info = ""
        investment = CONFIG.get("INVESTMENT_AMOUNT", 100)
        profit_liq = None
        profit_liq_percent = None
        invested_amount = None
        actual_qty = None

        # Jeśli osiągamy próg arbitrażu, sprawdzamy order booki
        if (profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]) or (profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]):
            order_book1 = await self.exchange1.fetch_order_book(symbol_ex1)
            order_book2 = await self.exchange2.fetch_order_book(symbol_ex2)
            if order_book1 is None or order_book2 is None:
                arbitrage_logger.warning(f"{self.pair_name} - Missing order book data for {asset}. Skipping liquidity check.")
            else:
                bids2 = order_book2.get('bids', [])
                asks1 = order_book1.get('asks', [])
                if not bids2 or not asks1:
                    arbitrage_logger.warning(f"{self.pair_name} - Insufficient order book data for {asset}. Skipping liquidity check.")
                else:
                    top_ask_ex1, available_buy_vol = asks1[0]
                    top_bid_ex2, available_sell_vol = bids2[0]
                    effective_order_buy = top_ask_ex1 * (1 + fee1/100)
                    desired_qty = investment / effective_order_buy
                    actual_qty = min(desired_qty, available_buy_vol, available_sell_vol)
                    effective_order_sell = top_bid_ex2 * (1 - fee2/100)
                    potential_proceeds = actual_qty * effective_order_sell
                    invested_amount = actual_qty * effective_order_buy
                    profit_liq = potential_proceeds - invested_amount
                    profit_liq_percent = (profit_liq / invested_amount * 100) if invested_amount else 0
                    liquidity_info = f"{names[0]} Top Ask: [{top_ask_ex1}, {available_buy_vol}]; {names[1]} Top Bid: [{top_bid_ex2}, {available_sell_vol}]"
                    extra_info = (f"Qty: {actual_qty:.4f}; Invested: {invested_amount:.2f}; "
                                  f"Proceeds: {potential_proceeds:.2f};")
        else:
            extra_info = "No liquidity check (threshold not met)."

        # Ustalamy quote – zakładamy, że obydwa symbole mają ten sam
        quote1 = symbol_ex1.split("/")[1] if "/" in symbol_ex1 else "N/A"
        quote2 = symbol_ex2.split("/")[1] if "/" in symbol_ex2 else "N/A"
        if quote1 != quote2:
            chosen_quote = quote1
            arbitrage_logger.warning(f"{self.pair_name} - Different quotes: {quote1} vs {quote2}, using {chosen_quote}.")
        else:
            chosen_quote = quote1

        profit_liq_percent_str = f"{profit_liq_percent:.2f}" if profit_liq_percent is not None else "N/A"
        profit_liq_str = f"{profit_liq:.6f}" if profit_liq is not None else "N/A"
        invested_amount_str = f"{invested_amount:.6f}" if invested_amount is not None else "N/A"
        actual_qty_str = f"{actual_qty:.4f}" if actual_qty is not None else "N/A"

        log_line = (
            f"Pair: {self.pair_name} | Asset: {asset} | "
            f"Buy ({names[0]} eff.): {effective_buy_ex1:.4f} | Sell ({names[1]} eff.): {effective_sell_ex2:.4f} | "
            f"Ticker Profit: {profit1:.2f}% | Liquidity Profit: {profit_liq_percent_str}% | "
            f"Profit ({chosen_quote}): {profit_liq_str} | Invested ({chosen_quote}): {invested_amount_str} | "
            f"Qty Purchased: {actual_qty_str} | Liquidity Info: {liquidity_info} | Extra: {extra_info}"
        )

        if profit_liq is not None and profit_liq > 0:
            opp_logger.info(log_line)
        else:
            unprofitable_logger.info(log_line)

        arbitrage_logger.info(
            f"{self.pair_name} - Opportunity: Buy on {self.exchange1.__class__.__name__} (price: {price1}, eff.: {effective_buy_ex1:.4f}) | "
            f"Sell on {self.exchange2.__class__.__name__} (price: {price2}, eff.: {effective_sell_ex2:.4f}) | "
            f"Ticker Profit: {profit1:.2f}% | Profit ({chosen_quote}): {profit_liq_str}"
        )
        if profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(
                f"{self.pair_name} - Opportunity: Buy on {self.exchange2.__class__.__name__} (price: {price2}, eff.: {effective_buy_ex2:.4f}) | "
                f"Sell on {self.exchange1.__class__.__name__} (price: {price1}, eff.: {effective_sell_ex1:.4f}) | "
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
    import asyncio
    from config import CONFIG
    asyncio.run(PairArbitrageStrategy(None, None, None).run())
