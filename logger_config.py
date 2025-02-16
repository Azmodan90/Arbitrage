import logging
from logging.handlers import RotatingFileHandler

def setup_logging():
    """
    Ustawia centralną konfigurację logowania:
      - Logger "app" zapisuje logi do pliku app.log z rotacją (max 5 MB, 5 kopii).
      - Dedykowane loggery: 'arbitrage', 'arbitrage_opportunities',
        'unprofitable_opportunities' i 'absurd_opportunities' mają własne pliki z rotacją.
    """
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Konfiguracja loggera globalnego "app"
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    if not app_logger.handlers:
        app_handler = RotatingFileHandler("app.log", mode="a", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
        app_handler.setFormatter(formatter)
        app_logger.addHandler(app_handler)

    # Logger dla strategii arbitrażowych
    arb_logger = logging.getLogger("arbitrage")
    arb_logger.setLevel(logging.INFO)
    arb_logger.propagate = False
    if not arb_logger.handlers:
        arb_handler = RotatingFileHandler("arbitrage.log", mode="a", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
        arb_handler.setFormatter(formatter)
        arb_logger.addHandler(arb_handler)

    # Logger dla opłacalnych okazji
    opp_logger = logging.getLogger("arbitrage_opportunities")
    opp_logger.setLevel(logging.INFO)
    opp_logger.propagate = False
    if not opp_logger.handlers:
        opp_handler = RotatingFileHandler("arbitrage_opportunities.log", mode="a", maxBytes=5*1024*1024, backupCount=False, encoding="utf-8")
        opp_handler.setFormatter(formatter)
        opp_logger.addHandler(opp_handler)

    # Logger dla nieopłacalnych okazji
    unprofitable_logger = logging.getLogger("unprofitable_opportunities")
    unprofitable_logger.setLevel(logging.INFO)
    unprofitable_logger.propagate = False
    if not unprofitable_logger.handlers:
        unprofitable_handler = RotatingFileHandler("unprofitable_opportunities.log", mode="a", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
        unprofitable_handler.setFormatter(formatter)
        unprofitable_logger.addHandler(unprofitable_handler)

    # Logger dla absurdalnych okazji
    absurd_logger = logging.getLogger("absurd_opportunities")
    absurd_logger.setLevel(logging.INFO)
    absurd_logger.propagate = False
    if not absurd_logger.handlers:
        absurd_handler = RotatingFileHandler("absurd_opportunities.log", mode="a", maxBytes=5*1024*1024, backupCount=5, encoding="utf-8")
        absurd_handler.setFormatter(formatter)
        absurd_logger.addHandler(absurd_handler)

    # Opcjonalnie, możesz ustawić root logger na wysoki poziom, żeby nie zbierał logów z modułów
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)

    return root_logger
