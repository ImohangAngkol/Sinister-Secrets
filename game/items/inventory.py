from copy import deepcopy


class Inventory:
    """Playthrough-owned items. Essential items have no drop/discard operation."""
    def __init__(self, definitions=None):
        self.keys = set()
        self.definitions = deepcopy(definitions or {})
        self.quantities = {}

    def add(self, item_id, quantity=1):
        definition = self.definitions.get(item_id, {})
        if not isinstance(quantity, int) or quantity <= 0:
            return False
        if definition.get("unique", definition.get("type") != "consumable"):
            if self.count(item_id):
                return False
            quantity = 1
        self.quantities[item_id] = self.count(item_id) + quantity
        if definition.get("type") == "key":
            self.keys.add(item_id)
        return True

    def count(self, item_id):
        return self.quantities.get(item_id, 0)

    def consume(self, item_id):
        if not self.count(item_id) or not self.definitions.get(item_id, {}).get("consumable"):
            return False
        self.quantities[item_id] -= 1
        if not self.quantities[item_id]:
            del self.quantities[item_id]
        return True

    def add_key(self, key_id: str):
        if key_id in self.keys:
            return False
        self.keys.add(key_id)
        self.quantities[key_id] = 1
        return True

    def has_key(self, key_id: str) -> bool:
        return key_id in self.keys

    def key_count(self) -> int:
        return len(self.keys)
