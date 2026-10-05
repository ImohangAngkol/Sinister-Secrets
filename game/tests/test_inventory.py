from game.items.inventory import Inventory


def test_inventory_key():
    inventory = Inventory()
    inventory.add_key("exit_key")

    assert inventory.has_key(
        "exit_key"
    )
