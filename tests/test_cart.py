import unittest
from models.cart import ShoppingCart

class TestShoppingCart(unittest.TestCase):
    def setUp(self):
        """Set up a shopping cart for testing."""
        self.cart = ShoppingCart()

    def test_add_item(self):
        """Test adding items to the cart."""
        self.cart.add_item("apple", 1.00)
        self.cart.add_item("banana", 0.50)
        self.assertEqual(self.cart.items["apple"], (1.00, 1))
        self.assertEqual(self.cart.items["banana"], (0.50, 1))

    def test_add_multiple_of_same_item(self):
        """Test adding multiple of the same item."""
        self.cart.add_item("apple", 1.00)
        self.cart.add_item("apple", 1.00)
        self.assertEqual(self.cart.items["apple"], (1.00, 2))

    def test_apply_discount(self):
        """Test applying a discount to items in the cart."""
        self.cart.add_item("apple", 1.00)
        self.cart.add_item("banana", 0.50)
        self.cart.apply_discount(10)
        self.assertAlmostEqual(self.cart.items["apple"][0], 0.90)
        self.assertAlmostEqual(self.cart.items["banana"][0], 0.45)

    def test_checkout(self):
        """Test checking out the cart."""
        self.cart.add_item("apple", 1.00)
        self.cart.add_item("banana", 0.50)
        self.cart.add_item("apple", 1.00)
        self.cart.apply_discount(10)
        total = self.cart.checkout()
        # (0.9 * 2) for apple and (0.45 * 1) for banana
        self.assertAlmostEqual(total, 2.25)

if __name__ == "__main__":
    unittest.main()