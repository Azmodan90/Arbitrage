import logging

def setup_logging():
    """
    Ustawia centralną konfigurację logowania:
      - Główny (root) logger zapisuje logi do pliku app.log
      - Dedykowane loggery: 'arbitrage', 'arbitrage_opportunities',
        'unprofitable_opportunities' i 'absurd_opportunities' zapisują logi do swoich plików.
      - Usunięto logowanie do terminala.
    """
    # Konfiguracja głównego (root) loggera
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Usuwamy wszystkie istniejące handlery
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Dodajemy file handler do root loggera (logi z działania programu)
    file_handler = logging.FileHandler("app.log", mode="a", encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Konfiguracja dedykowanego loggera "arbitrage"
    arbitrage_logger = logging.getLogger("arbitrage")
    if not arbitrage_logger.hasHandlers():
        arb_handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
        arb_handler.setFormatter(formatter)
        arbitrage_logger.addHandler(arb_handler)
        arbitrage_logger.setLevel(logging.INFO)
        arbitrage_logger.propagate = False  # zapobiega propagacji do root loggera

    # Logger dla okazji arbitrażowych (opłacalnych)
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
