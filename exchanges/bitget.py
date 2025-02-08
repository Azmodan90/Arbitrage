import aiohttp
import logging
from exchanges.exchange import Exchange

class BitgetExchange(Exchange):
    BASE_URL = "https://api.bitget.com"

    async def get_trading_pairs(self, session: aiohttp.ClientSession):
        """
        Pobiera listę dostępnych par dla rynku spot z Bitget.
        Używamy endpointu: GET /api/spot/v1/public/products
        Zwracamy listę słowników w formacie: {"symbol": <oryginalny symbol>, "base": <base>, "quote": <quote>}
        """
        url = f"{self.BASE_URL}/api/spot/v1/public/products"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_trading_pairs HTTP error: {response.status}")
                    return []
                data = await response.json()
                logging.info(f"Bitget get_trading_pairs response: {data}")
                # Akceptujemy kody sukcesu "00000" lub "200"
                if data.get("code") not in ["00000", "200"]:
                    logging.error(f"Bitget get_trading_pairs API error: {data.get('msg')}")
                    return []
                pairs = []
                known_quotes = ["USDT", "USD", "USDC", "EUR", "TRY", "BRL", "JPY", "TUSD", "FDUSD"]
                for item in data.get("data", []):
                    raw_symbol = item.get("symbol")
                    if raw_symbol:
                        # Najpierw sprawdzamy, czy symbol zawiera separator (np. '-' lub '/')
                        if '-' in raw_symbol:
                            parts = raw_symbol.split('-')
                        elif '/' in raw_symbol:
                            parts = raw_symbol.split('/')
                        else:
                            # Używamy listy znanych kwotowanych walut, aby wyodrębnić część bazową
                            parts = None
                            for quote in known_quotes:
                                if raw_symbol.endswith(quote) and len(raw_symbol) > len(quote):
                                    base = raw_symbol[:-len(quote)]
                                    parts = [base, quote]
                                    break
                            if not parts:
                                # Jeżeli nie uda się rozpoznać, zwróć cały symbol jako base
                                parts = [raw_symbol, ""]
                        if len(parts) >= 2:
                            pair_dict = {
                                "symbol": raw_symbol,
                                "base": parts[0],
                                "quote": parts[1]
                            }
                            pairs.append(pair_dict)
                        else:
                            pairs.append({
                                "symbol": raw_symbol,
                                "base": raw_symbol,
                                "quote": ""
                            })
                logging.info(f"Bitget trading pairs: {pairs}")
                return pairs
        except Exception as e:
            logging.exception("Bitget get_trading_pairs exception", exc_info=e)
            return []

    async def get_price(self, pair: str, session: aiohttp.ClientSession):
        """
        Pobiera bieżącą cenę dla podanej pary z Bitget.
        Używamy endpointu:
          GET /api/spot/v1/market/ticker?symbol=<pair>
        Jeśli w odpowiedzi nie ma pola 'last', próbuje użyć pola 'close'.
        """
        url = f"{self.BASE_URL}/api/spot/v1/market/ticker?symbol={pair}"
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logging.error(f"Bitget get_price HTTP error: {response.status} for {pair}")
                    return 0.0
                data = await response.json()
                if data.get("code") not in ["00000", "200"]:
                    logging.error(f"Bitget get_price API error: {data.get('msg')} for {pair}")
                    return 0.0
                price_str = data.get("data", {}).get("last")
                if price_str is None:
                    price_str = data.get("data", {}).get("close")
                    if price_str is None:
                        logging.error(f"Bitget get_price: brak pola 'last' lub 'close' dla {pair}")
                        return 0.0
                price = float(price_str)
                logging.info(f"Bitget price for {pair}: {price}")
                return price
        except Exception as e:
            logging.exception(f"Bitget get_price exception for {pair}: {e}")
            return 0.0
