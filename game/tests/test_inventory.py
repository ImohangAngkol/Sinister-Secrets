from game.items.inventory import Inventory
import unittest


def test_inventory_key():
    inventory = Inventory()
    inventory.add_key("exit_key")

    assert inventory.has_key(
        "exit_key"
    )


class InventoryTests(unittest.TestCase):
    def test_keys_are_unique(self):
        inventory = Inventory()
        self.assertFalse(inventory.has_key("exit_key"))
        inventory.add_key("exit_key")
        inventory.add_key("exit_key")
        self.assertTrue(inventory.has_key("exit_key"))
        self.assertEqual(inventory.key_count(), 1)
