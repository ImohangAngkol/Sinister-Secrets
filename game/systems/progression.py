"""Small per-playthrough puzzle state; no save system or global mutable state."""
class Progression:
    def __init__(self, house, player):
        self.house, self.player = house, player
        self.power_restored = False
        self.safe_unlocked = False
        self.boards_removed = False

    @property
    def objective(self):
        inventory = self.player.inventory
        if not self.player.has_flashlight:
            return "Collect the foyer flashlight."
        if not self.power_restored:
            return ("Install the fuse in the kitchen electrical box." if inventory.count("fuse")
                    else "Find the missing fuse in storage.")
        if not self.safe_unlocked:
            return "Read the household clues; open the dining lockbox."
        if not self.boards_removed:
            return "Use the crowbar on the boarded bedroom cabinet."
        if not inventory.has_key("exit_key"):
            return "Collect the exit key from the opened cabinet."
        return "Unlock the north exit and walk outside."

    def refresh(self):
        self.player.hud.set_objective(self.objective)

    def install_fuse(self):
        if self.power_restored:
            self.player.hud.show_message("The electrical lock already has power.")
            return False
        if not self.player.inventory.consume("fuse"):
            self.player.hud.show_message("A fuse is missing. Search the storage room.")
            return False
        self.power_restored = True
        self.house.pickups["kitchen_tally"].enabled = True
        self.house.puzzles["fuse_box"].color = self.house.puzzles["fuse_box"].powered_color
        self.house.puzzles["fuse_box"].interaction_text = "[E] Electrical box (powered)"
        self.player.hud.show_message("Power restored to the dining lockbox. A kitchen drawer opens.")
        self.refresh()
        return True

    def try_combination(self, digits):
        if self.safe_unlocked:
            return False
        if not self.power_restored:
            self.player.hud.show_message("The lockbox has no power. Its fuse is missing.")
            return False
        if digits != self.house.level.house["progression"]["combination"]:
            self.player.hud.show_message("Incorrect combination. The lock remains closed.")
            return False
        if not self.player.inventory.add("crowbar"):
            return False
        self.safe_unlocked = True
        self.house.puzzles["lockbox"].color = self.house.puzzles["lockbox"].powered_color
        self.house.puzzles["lockbox"].interaction_text = "[E] Lockbox (opened)"
        self.player.hud.show_message("Lockbox opened. Crowbar collected; it can pry the bedroom boards.")
        self.refresh()
        return True

    def remove_boards(self):
        if self.boards_removed:
            self.player.hud.show_message("The cabinet is already open.")
            return False
        if not self.player.inventory.count("crowbar"):
            self.player.hud.show_message("These boards need a crowbar. Investigate the dining lockbox.")
            return False
        self.boards_removed = True
        self.house.puzzles["boards"].enabled = False
        self.house.pickups["bedroom_exit_key"].enabled = True
        self.player.hud.show_message("Boards removed. The exit key is inside. Crowbar kept.")
        self.refresh()
        return True
