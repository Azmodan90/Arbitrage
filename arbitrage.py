import asyncio
from config import CONFIG

class ArbitrageStrategy:
    def __init__(self, exchanges):
        self.exchanges = exchanges  # Słownik z instancjami giełd

    async def check_opportunities(self, symbol):
        tickers = {}
        # Pobieramy tickery ze wszystkich giełd
        for name, exchange in self.exchanges.items():
            ticker = exchange.fetch_ticker(symbol)
            if ticker:
                tickers[name] = ticker['last']

        if tickers and len(tickers) >= 2:
            # Iterujemy po parach giełd
            for buy_name, buy_price in tickers.items():
                buy_fee = self.exchanges[buy_name].fee_rate
                # Efektywna cena zakupu = cena + opłata
                effective_buy = buy_price * (1 + buy_fee / 100)
                for sell_name, sell_price in tickers.items():
                    if sell_name == buy_name:
                        continue
                    sell_fee = self.exchanges[sell_name].fee_rate
                    # Efektywna cena sprzedaży = cena - opłata
                    effective_sell = sell_price * (1 - sell_fee / 100)
                    profit_percent = ((effective_sell - effective_buy) / effective_buy) * 100
                    if profit_percent >= CONFIG["ARBITRAGE_THRESHOLD"]:
                        print(f"Arbitrage opportunity detected for {symbol}!")
                        print(f"Buy on {buy_name} at {buy_price:.4f} (effective: {effective_buy:.4f})")
                        print(f"Sell on {sell_name} at {sell_price:.4f} (effective: {effective_sell:.4f})")
                        print(f"Potential profit: {profit_percent:.2f}%\n")
        await asyncio.sleep(1)  # Opóźnienie przed kolejnym sprawdzeniem

    async def run(self, symbol):
        while True:
            await self.check_opportunities(symbol)
