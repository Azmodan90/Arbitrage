import asyncio
import logging
import json
from config import CONFIG
from functools import partial

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

# Nowy logger dla absurdalnych okazji (zysk > 500%) – zapis do pliku absurd_opportunities.log
absurd_logger = logging.getLogger("absurd_opportunities")
if not absurd_logger.hasHandlers():
    absurd_handler = logging.FileHandler("absurd_opportunities.log", mode="a", encoding="utf-8")
    absurd_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    absurd_handler.setFormatter(absurd_formatter)
    absurd_logger.addHandler(absurd_handler)
    absurd_logger.setLevel(logging.INFO)
    absurd_logger.propagate = False

class PairArbitrageStrategy:
    def __init__(self, exchange1, exchange2, assets, pair_name=""):
        self.exchange1 = exchange1
        self.exchange2 = exchange2
        self.assets = assets  # lista symboli, np. ["GAME/USDT", "FARM/USDT", ...]
        self.pair_name = pair_name

    async def check_opportunity(self, symbol):
        arbitrage_logger.info(f"{self.pair_name} - Sprawdzam okazje arbitrażowe dla symbolu: {symbol}")
        loop = asyncio.get_running_loop()
        
        # Dla exchange1:
        if hasattr(self.exchange1, 'fetch_ticker_limited'):
            task1 = asyncio.create_task(self.exchange1.fetch_ticker_limited(symbol))
        else:
            task1 = loop.run_in_executor(None, self.exchange1.fetch_ticker, symbol)
        
        # Dla exchange2:
        if hasattr(self.exchange2, 'fetch_ticker_limited'):
            task2 = asyncio.create_task(self.exchange2.fetch_ticker_limited(symbol))
        else:
            task2 = loop.run_in_executor(None, self.exchange2.fetch_ticker, symbol)
        
        results = await asyncio.gather(task1, task2, return_exceptions=True)
        tickers = {}
        for key, result in zip(['ex1', 'ex2'], results):
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

        # Przykładowy filtr – jeśli zysk przekracza 500%, okazja jest uznawana za absurdalną.
        if profit1 > CONFIG["ABSURD_THRESHOLD"]:
            absurd_logger.warning(f"{self.pair_name} - Absurdally wysoki zysk dla {symbol}: {profit1:.2f}% (Kupno na {self.exchange1.__class__.__name__}, Sprzedaż na {self.exchange2.__class__.__name__}). Ignoruję okazję.")
        elif profit1 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} - Okazja arbitrażowa dla {symbol}: Kupno na {self.exchange1.__class__.__name__} "
                   f"(cena: {tickers['ex1']}, efektywna: {effective_buy_ex1:.4f}), sprzedaż na {self.exchange2.__class__.__name__} "
                   f"(cena: {tickers['ex2']}, efektywna: {effective_sell_ex2:.4f}), zysk: {profit1:.2f}%")
            arbitrage_logger.info(msg)
            opp_logger.info(msg)

        if profit2 > CONFIG["ABSURD_THRESHOLD"]:
            absurd_logger.warning(f"{self.pair_name} - Absurdally wysoki zysk dla {symbol}: {profit2:.2f}% (Kupno na {self.exchange2.__class__.__name__}, Sprzedaż na {self.exchange1.__class__.__name__}). Ignoruję okazję.")
        elif profit2 >= CONFIG["ARBITRAGE_THRESHOLD"]:
            msg = (f"{self.pair_name} - Okazja arbitrażowa dla {symbol}: Kupno na {self.exchange2.__class__.__name__} "
                   f"(cena: {tickers['ex2']}, efektywna: {effective_buy_ex2:.4f}), sprzedaż na {self.exchange1.__class__.__name__} "
                   f"(cena: {tickers['ex1']}, efektywna: {effective_sell_ex1:.4f}), zysk: {profit2:.2f}%")
            arbitrage_logger.info(msg)
            opp_logger.info(msg)


    async def run(self):
        arbitrage_logger.info(f"{self.pair_name} - Uruchamiam strategię arbitrażu dla {len(self.assets)} aktywów.")
        try:
            while True:
                for symbol in self.assets:
                    await self.check_opportunity(symbol)
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            arbitrage_logger.info(f"{self.pair_name} - Strategia arbitrażu została anulowana.")
            raise
