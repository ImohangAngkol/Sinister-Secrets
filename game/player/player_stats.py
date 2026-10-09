from collections import deque

from game.ghost.ghost_hearing import NoiseEvent
from game.settings import (FLASHLIGHT_START_BATTERY, NOISE_EVENT_LIFETIME,
                           STAMINA_MAX, STAMINA_DRAIN_PER_SECOND,
                           STAMINA_REGEN_DELAY, STAMINA_REGEN_PER_SECOND,
                           STAMINA_EXHAUSTED_RECOVERY)


class PlayerStats:
    def __init__(self):
        self.battery = float(
            FLASHLIGHT_START_BATTERY
        )

        self.noise_level = 0.0
        self.stamina = float(STAMINA_MAX)
        self.sprint_exhausted = False
        self.regen_delay = 0.0
        self.elapsed_time = 0.0
        self.noise_sequence = 0
        self.noise_events = deque(maxlen=64)

    def emit_noise(self, position, strength, kind="footstep"):
        if strength <= 0:
            return None
        self.noise_sequence += 1
        event = NoiseEvent(self.noise_sequence, tuple(position), float(strength),
                           self.elapsed_time, kind)
        self.noise_events.append(event)
        return event

    def advance(self, dt, sprint_seconds=0):
        dt = max(dt, 0)
        self.elapsed_time += dt
        while self.noise_events and self.elapsed_time - self.noise_events[0].created_at > NOISE_EVENT_LIFETIME:
            self.noise_events.popleft()
        if sprint_seconds > 0:
            self.stamina = max(0, self.stamina - STAMINA_DRAIN_PER_SECOND * sprint_seconds)
            self.regen_delay = STAMINA_REGEN_DELAY
            if self.stamina <= 1e-8:
                self.stamina = 0
                self.sprint_exhausted = True
        else:
            recovering = max(0, dt - self.regen_delay)
            self.regen_delay = max(0, self.regen_delay - dt)
            self.stamina = min(STAMINA_MAX, self.stamina + STAMINA_REGEN_PER_SECOND * recovering)
        if self.stamina >= STAMINA_EXHAUSTED_RECOVERY:
            self.sprint_exhausted = False
