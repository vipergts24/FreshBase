class ShoppingCart:
    def __init__(self):
        # Initialize an empty dict to hold items
        self.items = {}

    def add_item(self, name, price):
        # Add item to the cart with its price
        self.items[name] = price