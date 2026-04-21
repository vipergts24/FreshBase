class ShoppingCart:
    def __init__(self):
        # Initialize an empty dict to hold items
        self.items = {}

    def add_item(self, name, price):
        # Add item to the cart with its price
        self.items[name] = price

    def apply_discount(self, percentage):
        # Apply a discount to each item's price
        for name in self.items:
            original_price = self.items[name]
            discount_amount = (percentage / 100) * original_price
            discounted_price = original_price - discount_amount
            self.items[name] = discounted_price