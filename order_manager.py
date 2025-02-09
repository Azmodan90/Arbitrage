import logging

logging.basicConfig(level=logging.INFO)

class OrderManager:
    def __init__(self):
        self.orders = []

    def log_order(self, exchange_name, symbol, order_type, side, amount, price=None):
        order_details = {
            'exchange': exchange_name,
            'symbol': symbol,
            'order_type': order_type,
            'side': side,
            'amount': amount,
            'price': price if price else 'market'
        }
        self.orders.append(order_details)
        logging.info(f"Order simulated on {exchange_name}: {side} {amount} {symbol} at {price if price else 'market price'}")

    def get_orders(self):
        return self.orders
