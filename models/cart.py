class ShoppingCart:
    def __init__(self):
        """Initialize the shopping cart with an empty dictionary."""
        self.items = {}

    def add_item(self, name, price):
        """
        Add an item to the shopping cart.

        :param name: The name of the item.
        :param price: The price of the item.
        """
        if name in self.items:
            # If the item exists, increment the quantity
            current_price, current_quantity = self.items[name]
            self.items[name] = (current_price, current_quantity + 1)
        else:
            # If the item does not exist, add it with quantity 1
            self.items[name] = (price, 1)