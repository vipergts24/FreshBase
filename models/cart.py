class ShoppingCart:
    def __init__(self):
        """Initialize a new empty shopping cart."""
        self.items = {}

    def add_item(self, name, price):
        """Add an item to the shopping cart.

        Args:
            name (str): The name of the item.
            price (float): The price of the item.
        """
        if name in self.items:
            self.items[name] += price
        else:
            self.items[name] = price