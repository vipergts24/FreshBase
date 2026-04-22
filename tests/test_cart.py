import unittest
from models.cart import ShoppingCart

class TestShoppingCart(unittest.TestCase):
    def setUp(self):
        self.cart = ShoppingCart()

    def test_add_item(self):
        self.cart.add_item("apple", 1.0)
        self.cart.add_item("banana", 2.0)
        self.assertEqual(self.cart.items, {"apple": 1.0, "banana": 2.0})

    def test_apply_discount(self):
        self.cart.add_item("apple", 1.0)
        self.cart.add_item("banana", 2.0)
        self.cart.apply_discount(10)  # Apply 10% discount
        self.assertAlmostEqual(self.cart.items["apple"], 0.9)
        self.assertAlmostEqual(self.cart.items["banana"], 1.8)

    def test_checkout(self):
        self.cart.add_item("apple", 1.0)
        self.cart.add_item("banana", 2.0)
        self.cart.apply_discount(10)  # Apply 10% discount
        total = self.cart.checkout()
        self.assertAlmostEqual(total, 2.7)  # 0.9 + 1.8

if __name__ == "__main__":
    unittest.main()