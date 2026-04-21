import unittest
from models.cart import ShoppingCart

class TestShoppingCart(unittest.TestCase):

    def setUp(self):
        self.cart = ShoppingCart()

    def test_add_item(self):
        self.cart.add_item('Apple', 1.00)
        self.assertEqual(self.cart.items, {'Apple': 1.00})

    def test_apply_discount(self):
        self.cart.add_item('Banana', 2.00)
        self.cart.apply_discount(10)
        self.assertAlmostEqual(self.cart.items['Banana'], 1.80)

    def test_checkout(self):
        self.cart.add_item('Apple', 1.00)
        self.cart.add_item('Banana', 1.50)
        self.assertEqual(self.cart.checkout(), 2.50)

    def test_apply_discount_and_checkout(self):
        self.cart.add_item('Orange', 3.00)
        self.cart.apply_discount(50)
        self.assertEqual(self.cart.checkout(), 1.50)

if __name__ == '__main__':
    unittest.main()