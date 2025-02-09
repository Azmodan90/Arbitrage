import asyncio

class ArbitrageStrategy:
    def __init__(self, exchanges):
        self.exchanges = exchanges  # Słownik z instancjami giełd

    async def check_opportunities(self, symbol):
        prices = {}
        for name, exchange in self.exchanges.items():
            ticker = exchange.fetch_ticker(symbol)
            if ticker:
                prices[name] = ticker['last']
        if prices:
            min_price = min(prices.values())
            max_price = max(prices.values())
            diff_percent = ((max_price - min_price) / min_price) * 100
            # Logujemy okazję, gdy różnica procentowa przekracza próg (np. 0.5%)
            if diff_percent >= 0.5:
                print(f"Arbitrage opportunity detected for {symbol}! Price difference: {diff_percent:.2f}%")
                # W przyszłości można dodać wywołanie order_manager do składania zleceń
        await asyncio.sleep(1)  # Opóźnienie przed kolejnym sprawdzeniem

    async def run(self, symbol):
        while True:
            await self.check_opportunities(symbol)
