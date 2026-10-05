class Inventory:
    def __init__(self):
        self.keys = set()

    def add_key(self, key_id: str):
        self.keys.add(key_id)

    def has_key(self, key_id: str) -> bool:
        return key_id in self.keys

    def key_count(self) -> int:
        return len(self.keys)
