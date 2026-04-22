class ShoppingCart:
    def __init__(self):
        # Initializes the cart with an empty dictionary
        self.cart_items = {}

    def add_item(self, name, price):
        # If the item is already in the cart, increment the quantity
        if name in self.cart_items:
            self.cart_items[name]['quantity'] += 1
        else:
            # If the item is new, add it with the given price and a quantity of 1
            self.cart_items[name] = {'price': price, 'quantity': 1}

    def __str__(self):
        # This is for better visualization of the cart's contents
        return str(self.cart_items)