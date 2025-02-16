import logging

def setup_logging():
    """
    Ustawia centralną konfigurację logowania.
    Tworzy dedykowane loggery:
      - "app": logi globalne (aplikacyjne) trafiają do app.log
      - "arbitrage": logi strategii arbitrażowych trafiają do arbitrage.log
      - "arbitrage_opportunities": trafiają do arbitrage_opportunities.log
      - "unprofitable_opportunities": trafiają do unprofitable_opportunities.log
      - "absurd_opportunities": trafiają do absurd_opportunities.log
    Root logger nie posiada żadnych handlerów – komunikaty z niego (jeśli się pojawią) nie będą zapisywane.
    """
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

    # Logger globalny "app"
    app_logger = logging.getLogger("app")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    if not app_logger.handlers:
        app_handler = logging.FileHandler("app.log", mode="a", encoding="utf-8")
        app_handler.setFormatter(formatter)
        app_logger.addHandler(app_handler)

    # Logger dla strategii arbitrażowych
    arb_logger = logging.getLogger("arbitrage")
    arb_logger.setLevel(logging.INFO)
    arb_logger.propagate = False
    if not arb_logger.handlers:
        arb_handler = logging.FileHandler("arbitrage.log", mode="a", encoding="utf-8")
        arb_handler.setFormatter(formatter)
        arb_logger.addHandler(arb_handler)

    # Logger dla opłacalnych okazji
    opp_logger = logging.getLogger("arbitrage_opportunities")
    opp_logger.setLevel(logging.INFO)
    opp_logger.propagate = False
    if not opp_logger.handlers:
        opp_handler = logging.FileHandler("arbitrage_opportunities.log", mode="a", encoding="utf-8")
        opp_handler.setFormatter(formatter)
        opp_logger.addHandler(opp_handler)

    # Logger dla nieopłacalnych okazji
    unprofitable_logger = logging.getLogger("unprofitable_opportunities")
    unprofitable_logger.setLevel(logging.INFO)
    unprofitable_logger.propagate = False
    if not unprofitable_logger.handlers:
        unprofitable_handler = logging.FileHandler("unprofitable_opportunities.log", mode="a", encoding="utf-8")
        unprofitable_handler.setFormatter(formatter)
        unprofitable_logger.addHandler(unprofitable_handler)

    # Logger dla absurdalnych okazji
    absurd_logger = logging.getLogger("absurd_opportunities")
    absurd_logger.setLevel(logging.INFO)
    absurd_logger.propagate = False
    if not absurd_logger.handlers:
        absurd_handler = logging.FileHandler("absurd_opportunities.log", mode="a", encoding="utf-8")
        absurd_handler.setFormatter(formatter)
        absurd_logger.addHandler(absurd_handler)

    # Upewnij się, że root logger nie posiada żadnych handlerów – zapobiega to powielaniu logów
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.WARNING)  # tylko ostrzeżenia i błędy trafiają do root loggera

    return root_logger
