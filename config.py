import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "BINANCE_API_KEY": os.getenv("BINANCE_API_KEY"),
    "BINANCE_SECRET": os.getenv("BINANCE_SECRET"),
    "KUCOIN_API_KEY": os.getenv("KUCOIN_API_KEY"),
    "KUCOIN_SECRET": os.getenv("KUCOIN_SECRET"),
    "BITGET_API_KEY": os.getenv("BITGET_API_KEY"),
    "BITGET_SECRET": os.getenv("BITGET_SECRET"),
    "BITSTAMP_API_KEY": os.getenv("BITSTAMP_API_KEY"),
    "BITSTAMP_SECRET": os.getenv("BITSTAMP_SECRET"),
    
    "ALLOWED_QUOTES": ["USDT", "EUR",],

    "MIN_LIQUIDITY": 300,  # minimalny wolumen (możesz ustalić własną wartość)

    "ARBITRAGE_THRESHOLD": 2,  # próg arbitrażu w %

    "ABSURD_THRESHOLD": 100,     # próg absurdalnego zysku w %

    "INVESTMENT_AMOUNT": 500,    # kwota inwestycji (domyślnie w USDT)
    
    "CONVERT_INVESTMENT": {
        "BTC": True,
        "ETH": True

            },
    "FILTER_LOW_LIQUIDITY": True,
    "MIN_LIQUIDITY": {
        
        "USDT": 1000,   # minimalny wolumen (sumarycznie z N poziomów) dla USDT
        "EUR": 50,      # dla EUR
        "BTC": 0.05     # dla BTC
    },
    "LIQUIDITY_LEVELS_TO_CHECK": 3  # liczba pierwszych poziomów order booka do zsumowania
}

