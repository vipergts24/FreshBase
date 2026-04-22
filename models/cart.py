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

    def apply_discount(self, percentage):
        """
        Apply a discount to all items in the shopping cart.

        :param percentage: The discount percentage to apply.
        """
        for name in self.items:
            price, quantity = self.items[name]
            discounted_price = price * (1 - percentage / 100)
            self.items[name] = (discounted_price, quantity)

    def checkout(self):
        """
        Calculate and return the total sum of items in the shopping cart.

        :return: The total sum of all items' prices multiplied by their quantities.
        """
        total = 0
        for price, quantity in self.items.values():
            total += price * quantity
        return total