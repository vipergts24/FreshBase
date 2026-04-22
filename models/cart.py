class ShoppingCart:
    def __init__(self):
        # Initialize an empty dictionary to store items
        self.items = {}

    def add_item(self, name, price):
        """Add an item to the shopping cart.

        Args:
            name (str): The name of the item.
            price (float): The price of the item.
        """
        if not isinstance(name, str) or not isinstance(price, (int, float)):
            raise ValueError("Invalid name or price type.")
        
        if price < 0:
            raise ValueError("Price cannot be negative.")
        
        self.items[name] = price