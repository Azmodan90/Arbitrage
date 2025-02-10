import requests
import logging

# Konfiguracja logowania do pliku "token_check.log"
logging.basicConfig(
    level=logging.INFO,
    filename="token_check.log",
    filemode="a",
    format="%(asctime)s - %(levelname)s - %(message)s"
)

def log_and_print(message):
    print(message)
    logging.info(message)

def fetch_coin_list():
    url = "https://api.coingecko.com/api/v3/coins/list"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

def search_token(symbol, coins):
    symbol = symbol.lower()
    matches = [coin for coin in coins if coin["symbol"] == symbol]
    return matches

def fetch_tickers(coin_id):
    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
    response = requests.get(url, params={"include_exchange_logo": "false"}, timeout=10)
    response.raise_for_status()
    return response.json()

def main():
    token_symbol = input("Podaj symbol tokena (np. GAME): ").strip()
    coins = fetch_coin_list()
    matches = search_token(token_symbol, coins)
    if not matches:
        log_and_print("Nie znaleziono tokenów o podanym symbolu.")
        return

    log_and_print("Znalezione tokeny:")
    for i, coin in enumerate(matches, start=1):
        log_and_print(f"{i}. ID: {coin['id']} - Name: {coin['name']} - Symbol: {coin['symbol']}")

    choice = input("Wybierz numer odpowiedniego tokena: ").strip()
    try:
        selected = matches[int(choice) - 1]
    except (ValueError, IndexError):
        log_and_print("Nieprawidłowy wybór.")
        return

    coin_id = selected["id"]
    tickers_data = fetch_tickers(coin_id)
    tickers = tickers_data.get("tickers", [])
    if not tickers:
        log_and_print("Brak tickerów dla tego tokena.")
        return

    log_and_print(f"\nToken {selected['name']} (ID: {coin_id}) jest notowany na następujących giełdach:")
    for ticker in tickers:
        exchange = ticker.get("market", {}).get("name")
        base = ticker.get("base")
        target = ticker.get("target")
        log_and_print(f"- {exchange}: {base}/{target}")

if __name__ == "__main__":
    main()
