class ShoppingCart:
    def __init__(self):
        # Initialize an empty dictionary to store item name and price pairs
        self.items = {}

    def add_item(self, name, price):
        # Add or update items with their price in the cart
        self.items[name] = price

    def apply_discount(self, percentage):
        # Apply a percentage discount to all items in the cart
        for item in self.items:
            original_price = self.items[item]
            discount_amount = original_price * (percentage / 100)
            new_price = original_price - discount_amount
            self.items[item] = new_price

    def checkout(self):
        # Return the total sum of all the item's prices in the cart
        return sum(self.items.values())