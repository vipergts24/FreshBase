class ShoppingCart:
    def __init__(self):
        self.items = {}

    def add_item(self, name, price):
        self.items[name] = price
    
    def apply_discount(self, percentage):
        for item in self.items:
            original_price = self.items[item]
            discount_amount = original_price * (percentage / 100)
            new_price = original_price - discount_amount
            self.items[item] = new_price