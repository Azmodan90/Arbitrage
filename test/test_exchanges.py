# test/test_exchanges.py

import sys
import os
# Dodaj katalog główny projektu do sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
import aiohttp
from exchanges.binance import BinanceExchange

def fake_get(*args, **kwargs):
    class FakeResponse:
        async def json(self):
            return {
                "symbols": [
                    {"symbol": "BTCUSDT", "status": "TRADING"},
                    {"symbol": "ETHUSDT", "status": "TRADING"},
                    {"symbol": "XRPUSDT", "status": "BREAK"}
                ]
            }
        @property
        def status(self):
            return 200
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            pass
    return FakeResponse()

@pytest.mark.asyncio
async def test_binance_get_trading_pairs(monkeypatch):
    monkeypatch.setattr(aiohttp.ClientSession, "get", fake_get)
    exchange = BinanceExchange()
    async with aiohttp.ClientSession() as session:
        pairs = await exchange.get_trading_pairs(session)
    assert "BTCUSDT" in pairs
    assert "ETHUSDT" in pairs
    assert "XRPUSDT" not in pairs

@pytest.mark.asyncio
async def test_calculate_difference():
    from main import calculate_difference
    diff = calculate_difference(100, 110)
    assert round(diff, 2) == 10.0
    diff = calculate_difference(110, 100)
    assert round(diff, 2) == 10.0
    diff = calculate_difference(0, 100)
    assert diff == 0.0
