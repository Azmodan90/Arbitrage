import logging

def setup_logging():
    """
    Ustawia konfigurację logowania dla całej aplikacji oraz dedykowanych loggerów.
    """
    # Konfiguracja głównego loggera
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Usuwamy istniejące handlery
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Dodajemy handler konsolowy (opcjonalnie)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Konfiguracja loggera dla arbitrażu
    arbitrage_logger = logging.getLogger("arbitrage")
    if not arbitrage_logger.hasHandlers():
        file_handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
        file_handler.setFormatter(formatter)
        arbitrage_logger.addHandler(file_handler)
        arbitrage_logger.setLevel(logging.INFO)
        arbitrage_logger.propagate = False

    # Logger dla okazji arbitrażowych
    opp_logger = logging.getLogger("arbitrage_opportunities")
    if not opp_logger.hasHandlers():
        opp_handler = logging.FileHandler("arbitrage_opportunities.log", mode="a", encoding="utf-8")
        opp_handler.setFormatter(formatter)
        opp_logger.addHandler(opp_handler)
        opp_logger.setLevel(logging.INFO)
        opp_logger.propagate = False

    # Logger dla nieopłacalnych okazji
    unprofitable_logger = logging.getLogger("unprofitable_opportunities")
    if not unprofitable_logger.hasHandlers():
        unprofitable_handler = logging.FileHandler("unprofitable_opportunities.log", mode="a", encoding="utf-8")
        unprofitable_handler.setFormatter(formatter)
        unprofitable_logger.addHandler(unprofitable_handler)
        unprofitable_logger.setLevel(logging.INFO)
        unprofitable_logger.propagate = False

    # Logger dla absurdalnych okazji
    absurd_logger = logging.getLogger("absurd_opportunities")
    if not absurd_logger.hasHandlers():
        absurd_handler = logging.FileHandler("absurd_opportunities.log", mode="a", encoding="utf-8")
        absurd_handler.setFormatter(formatter)
        absurd_logger.addHandler(absurd_handler)
        absurd_logger.setLevel(logging.INFO)
        absurd_logger.propagate = False

    return root_logger
