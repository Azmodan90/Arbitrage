import asyncio
import logging
from config import CONFIG
from functools import partial

# Konfiguracja oddzielnego loggera dla logów arbitrażu
arbitrage_logger = logging.getLogger("arbitrage")
if not arbitrage_logger.hasHandlers():
    handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    arbitrage_logger.addHandler(handler)
    arbitrage_logger.setLevel(logging.INFO)
    # Wyłącz propagację, aby logi nie trafiały do app.log
    arbitrage_logger.propagate = False

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        self.assets = assets  # lista symboli, np. ["BTC/USDT", "ETH/USDT", ...]
        self.pair_name = pair_name

    async def check_opportunity(self, symbol):
        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam okazje arbitrażowe dla symbolu: {symbol}")
        loop = asyncio.get_running_loop()
        tasks = {
            'ex1': loop.run_in_executor(None, partial(self.exchange1.fetch_ticker, symbol)),
            'ex2': loop.run_in_executor(None, partial(self.exchange2.fetch_ticker, symbol))
        }
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        tickers = {}
        for key, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                arbitrage_logger.error(f"{self.pair_name} - Błąd pobierania danych dla {key}: {result}")
            elif result:
                price = result.get('last')
                if price is None:
                    arbitrage_logger.warning(f"{self.pair_name} - Dla {key} pobrana cena jest None, pomijam {symbol}")
                else:
                    tickers[key] = price
                    arbitrage_logger.info(f"{self.pair_name} - {key}: pobrana cena = {price}")
        if tickers.get('ex1') is None or tickers.get('ex2') is None:
            arbitrage_logger.warning(f"{self.pair_name} - Niedostateczne dane dla {symbol}, pomijam ten symbol.")
            return

        fee1 = self.exchange1.fee_rate
        fee2 = self.exchange2.fee_rate

        effective_buy_ex1 = tickers['ex1'] * (1 + fee1 / 100)
        effective_sell_ex2 = tickers['ex2'] * (1 - fee2 / 100)
        profit1 = ((effective_sell_ex2 - effective_buy_ex1) / effective_buy_ex1) * 100

        effective_buy_ex2 = tickers['ex2'] * (1 + fee2 / 100)
        effective_sell_ex1 = tickers['ex1'] * (1 - fee1 / 100)
        profit2 = ((effective_sell_ex1 - effective_buy_ex2) / effective_buy_ex2) * 100

        if profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(f"{self.pair_name} - Okazja arbitrażowa dla {symbol}: Kupno na {self.exchange1.__class__.__name__} (cena: {tickers['ex1']}, efektywna: {effective_buy_ex1:.4f}), sprzedaż na {self.exchange2.__class__.__name__} (cena: {tickers['ex2']}, efektywna: {effective_sell_ex2:.4f}), zysk: {profit1:.2f}%")
        if profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            arbitrage_logger.info(f"{self.pair_name} - Okazja arbitrażowa dla {symbol}: Kupno na {self.exchange2.__class__.__name__} (cena: {tickers['ex2']}, efektywna: {effective_buy_ex2:.4f}), sprzedaż na {self.exchange1.__class__.__name__} (cena: {tickers['ex1']}, efektywna: {effective_sell_ex1:.4f}), zysk: {profit2:.2f}%")

    async def run(self):
        arbitrage_logger.info(f"{self.pair_name} - Uruchamiam strategię arbitrażu dla {len(self.assets)} aktywów.")
        while True:
            for symbol in self.assets:
                await self.check_opportunity(symbol)
            await asyncio.sleep(1)
