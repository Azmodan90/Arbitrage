# utils.py

def calculate_effective_buy(price, fee_rate):
    """
    Oblicza efektywną cenę zakupu przy uwzględnieniu opłaty.
    :param price: cena rynkowa
    :param fee_rate: opłata w procentach
    :return: efektywna cena zakupu
    """
    return price * (1 + fee_rate / 100)

def calculate_effective_sell(price, fee_rate):
    """
    Oblicza efektywną cenę sprzedaży przy uwzględnieniu opłaty.
    :param price: cena rynkowa
    :param fee_rate: opłata w procentach
    :return: efektywna cena sprzedaży
    """
    return price * (1 - fee_rate / 100)
def calculate_effective_buy(price, fee_rate):
    return price * (1 + fee_rate / 100)

def calculate_effective_sell(price, fee_rate):
    return price * (1 - fee_rate / 100)
