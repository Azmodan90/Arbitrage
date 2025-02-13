def calculate_effective_buy(price, fee_rate):
    return price * (1 + fee_rate / 100)

def calculate_effective_sell(price, fee_rate):
    return price * (1 - fee_rate / 100)
