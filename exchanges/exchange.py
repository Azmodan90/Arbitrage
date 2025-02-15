# exchange.py

class Exchange:
    async def get_trading_pairs(self):
        raise NotImplementedError("Metoda get_trading_pairs() musi być zaimplementowana.")

    async def get_price(self, symbol: str) -> float:
        raise NotImplementedError("Metoda get_price() musi być zaimplementowana.")

    async def close(self):
        raise NotImplementedError("Metoda close() musi być zaimplementowana.")
