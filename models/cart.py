class ShoppingCart:
    def __init__(self):
        # Initialize an empty dictionary to store item name and price pairs
        self.items = {}

    def add_item(self, name, price):
        # Add or update items with their price in the cart
        self.items[name] = price