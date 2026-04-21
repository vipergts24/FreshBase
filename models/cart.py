class ShoppingCart:
    def __init__(self):
        # Initialize an empty dictionary to store items
        # Key: item name, Value: item price
        self.items = {}

    def add_item(self, name, price):
        """
        Add an item with its price to the shopping cart.
        If the item already exists, update its price.
        
        :param name: The name of the item.
        :param price: The price of the item.
        """
        self.items[name] = price

    def __repr__(self):
        """
        Provide a string representation of the shopping cart's contents.
        
        :return: A string that lists all items and their prices.
        """
        return f"ShoppingCart({self.items})"