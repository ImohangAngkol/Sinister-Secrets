from game.items.inventory import Inventory
import unittest


def test_inventory_key():
    inventory = Inventory()
    inventory.add_key("exit_key")

    assert inventory.has_key(
        "exit_key"
    )


class InventoryTests(unittest.TestCase):
    def test_quantities_and_only_consumable_items_can_be_removed(self):
        inventory = Inventory({'battery': {'type':'consumable', 'consumable':True},
                               'crowbar': {'type':'tool', 'unique':True}})
        self.assertTrue(inventory.add('battery', 3))
        self.assertEqual(inventory.count('battery'), 3)
        self.assertTrue(inventory.consume('battery'))
        self.assertEqual(inventory.count('battery'), 2)
        self.assertTrue(inventory.add('crowbar'))
        self.assertFalse(inventory.consume('crowbar'))
        self.assertEqual(inventory.count('crowbar'), 1)

    def test_unique_notes_tools_and_keys_reject_duplicates(self):
        inventory = Inventory({'note': {'type':'note'}, 'tool': {'type':'tool'}, 'key': {'type':'key'}})
        for item in ('note','tool','key'):
            self.assertTrue(inventory.add(item))
            self.assertFalse(inventory.add(item))
            self.assertEqual(inventory.count(item), 1)
        self.assertTrue(inventory.has_key('key'))

    def test_invalid_quantities_and_missing_consumption_do_not_change_inventory(self):
        inventory = Inventory({'battery': {'type':'consumable', 'consumable':True}})
        for quantity in (0, -1, 1.5):
            self.assertFalse(inventory.add('battery',quantity))
        self.assertFalse(inventory.consume('battery'))
        self.assertEqual(inventory.quantities, {})
    def test_keys_are_unique(self):
        inventory = Inventory()
        self.assertFalse(inventory.has_key("exit_key"))
        inventory.add_key("exit_key")
        inventory.add_key("exit_key")
        self.assertTrue(inventory.has_key("exit_key"))
        self.assertEqual(inventory.key_count(), 1)
