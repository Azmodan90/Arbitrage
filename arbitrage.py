import asyncio
import aiohttp
import logging
from typing import Dict, Optional

# Konfiguracja logowania
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Klasa bazowa reprezentująca giełdę
class Exchange:
    def __init__(self, name: str):
        self.name = name

    async def get_price(self, asset: str, session: aiohttp.ClientSession) -> Optional[float]:
        """
        Metoda powinna zwracać aktualną cenę aktywa.
        """
        raise NotImplementedError

# Implementacja dla Binance
class Binance(Exchange):
    def __init__(self):
        super().__init__('Binance')

    async def get_price(self, asset: str, session: aiohttp.ClientSession) -> Optional[float]:
        # Na Binance pary są notowane jako np. BTCUSDT
        symbol = asset.upper() + "USDT"
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data["price"])
                    return price
                else:
                    logging.error(f"{self.name}: HTTP error {response.status} dla aktywa {asset}")
                    return None
        except Exception as e:
            logging.exception(f"{self.name}: Błąd podczas pobierania ceny dla {asset}: {e}")
            return None

# Implementacja dla Coinbase
class Coinbase(Exchange):
    def __init__(self):
        super().__init__('Coinbase')

    async def get_price(self, asset: str, session: aiohttp.ClientSession) -> Optional[float]:
        # Na Coinbase używamy pary w formacie np. BTC-USD
        symbol = asset.upper() + "-USD"
        url = f"https://api.coinbase.com/v2/prices/{symbol}/spot"
        try:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # Struktura: { "data": { "base": "BTC", "currency": "USD", "amount": "..." } }
                    price = float(data["data"]["amount"])
                    return price
                else:
                    logging.error(f"{self.name}: HTTP error {response.status} dla aktywa {asset}")
                    return None
        except Exception as e:
            logging.exception(f"{self.name}: Błąd podczas pobierania ceny dla {asset}: {e}")
            return None

async def fetch_prices(asset: str, exchanges: Dict[str, Exchange], session: aiohttp.ClientSession) -> Dict[str, Optional[float]]:
    """
    Pobiera ceny danego aktywa z wszystkich giełd.
    """
    prices = {}
    tasks = []
    for name, exchange in exchanges.items():
        task = asyncio.create_task(exchange.get_price(asset, session))
        tasks.append((name, task))
    for name, task in tasks:
        price = await task
        prices[name] = price
    return prices

async def analyze_asset(asset: str, exchanges: Dict[str, Exchange], session: aiohttp.ClientSession, threshold: float):
    """
    Analizuje różnice cen dla danego aktywa i loguje okazje arbitrażowe, 
    gdy różnica przekracza próg threshold (w procentach).
    """
    prices = await fetch_prices(asset, exchanges, session)
    logging.info(f"Ceny dla {asset}: {prices}")

    # Porównanie cen pomiędzy każdą parą giełd
    exchange_names = list(prices.keys())
    for i in range(len(exchange_names)):
        for j in range(i + 1, len(exchange_names)):
            ex1 = exchange_names[i]
            ex2 = exchange_names[j]
            price1 = prices[ex1]
            price2 = prices[ex2]

            if price1 is None or price2 is None:
                continue

            # Obliczamy różnicę procentową w stosunku do niższej ceny
            if price1 < price2:
                diff = (price2 - price1) / price1 * 100
                if diff >= threshold:
                    logging.info(
                        f"Okazja arbitrażowa dla {asset}: Kup na {ex1} po {price1:.2f}, sprzedaj na {ex2} po {price2:.2f} (różnica: {diff:.2f}%)"
                    )
            else:
                diff = (price1 - price2) / price2 * 100
                if diff >= threshold:
                    logging.info(
                        f"Okazja arbitrażowa dla {asset}: Kup na {ex2} po {price2:.2f}, sprzedaj na {ex1} po {price1:.2f} (różnica: {diff:.2f}%)"
                    )

async def main():
    # Definicja giełd do analizy
    exchanges = {
        "binance": Binance(),
        "coinbase": Coinbase(),
    }

    # Lista aktywów do monitorowania (np. BTC, ETH)
    assets = ["BTC", "ETH"]
    # Minimalna różnica procentowa, aby uznać okazję za arbitrażową
    threshold = 1.0  # np. 1%

    async with aiohttp.ClientSession() as session:
        while True:
            for asset in assets:
                await analyze_asset(asset, exchanges, session, threshold)
            # Odczekaj 10 sekund przed kolejną rundą analizy – wartość tę można dostosować
            await asyncio.sleep(10)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Program zatrzymany przez użytkownika")
