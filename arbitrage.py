# arbitrage.py
import asyncio
import logging
from config import CONFIG
from functools import partial

class ArbitrageStrategy:
    def __init__(self, exchanges):
        self.exchanges = exchanges  # Słownik z instancjami giełd

    async def check_opportunities(self, symbol):
        logging.info(f"Sprawdzam okazje arbitrażowe dla symbolu: {symbol}")
        loop = asyncio.get_running_loop()
        # Równoległe pobieranie danych: wysyłamy żądania do wszystkich giełd jednocześnie
        tasks = {
            name: loop.run_in_executor(None, partial(exchange.fetch_ticker, symbol))
            for name, exchange in self.exchanges.items()
        }
        logging.info("Wysłano równoległe żądania do giełd.")
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        tickers = {}
        for name, result in zip(tasks.keys(), results):
            if isinstance(result, Exception):
                logging.error(f"Błąd pobierania danych dla {name}: {result}")
            elif result:
                ticker_value = result.get('last')
                tickers[name] = ticker_value
                logging.info(f"{name}: pobrana cena = {ticker_value}")

        if tickers and len(tickers) >= 2:
            for buy_name, buy_price in tickers.items():
                buy_fee = self.exchanges[buy_name].fee_rate
                effective_buy = buy_price * (1 + buy_fee / 100)
                for sell_name, sell_price in tickers.items():
                    if sell_name == buy_name:
                        continue
                    sell_fee = self.exchanges[sell_name].fee_rate
                    effective_sell = sell_price * (1 - sell_fee / 100)
                    profit_percent = ((effective_sell - effective_buy) / effective_buy) * 100
                    if profit_percent >= CONFIG["ARBITRAGE_THRESHOLD"]:
                        logging.info("OKAZJA ARBITRAŻOWA!")
                        logging.info(f"{symbol} - Kupno na {buy_name}: cena = {buy_price:.4f}, efektywna cena = {effective_buy:.4f}")
                        logging.info(f"{symbol} - Sprzedaż na {sell_name}: cena = {sell_price:.4f}, efektywna cena = {effective_sell:.4f}")
                        logging.info(f"Potencjalny zysk: {profit_percent:.2f}%")
        else:
            logging.info("Niewystarczające dane do analizy okazji arbitrażu.")
        await asyncio.sleep(1)

    async def run(self, symbol):
        logging.info("Uruchamiam strategię arbitrażu...")
        while True:
            await self.check_opportunities(symbol)
