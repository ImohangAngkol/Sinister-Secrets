WINDOW_TITLE = "Sinister Secrets"

# PLAYER
PLAYER_SPEED = 5
PLAYER_SPRINT_SPEED = 8
PLAYER_HEIGHT = 1.8
INTERACT_DISTANCE = 2.5
PLAYER_CROUCH_HEIGHT = 1.0
PLAYER_CROUCH_SPEED = 2.2
PLAYER_CROUCH_NOISE = 0.7
PLAYER_CAMERA_HEIGHT_RESPONSE = 12
STAMINA_MAX = 100
STAMINA_DRAIN_PER_SECOND = 22
STAMINA_REGEN_PER_SECOND = 15
STAMINA_REGEN_DELAY = 1.0
STAMINA_EXHAUSTED_RECOVERY = 25
NOISE_EVENT_LIFETIME = 1.5
WALK_NOISE_STRIDE = 1.5
SPRINT_NOISE_STRIDE = 2.0
CROUCH_NOISE_STRIDE = 1.5
HIDING_SAFE_SECONDS = 12
HIDING_NOISE_INTERVAL = 3
HIDING_NOISE_LEVEL = 4
HIDING_LOOK_YAW = 25
HIDING_LOOK_PITCH = 20
HIDING_REENTRY_DELAY = 1.0

# FLASHLIGHT
MAX_BATTERY = 100
FLASHLIGHT_START_BATTERY = 65
FLASHLIGHT_DRAIN_PER_SECOND = 0.25  # 400 seconds total with the authored 65+35 supply.
LOW_BATTERY_THRESHOLD = 15

# LIGHTING (normalized RGB intensities; lights may exceed 1, distances in units)
HOUSE_AMBIENT_COLOR = (0.10, 0.11, 0.14)
HOUSE_FILL_COLOR = (0.015, 0.018, 0.025)
HOUSE_FOG_COLOR = (0.006, 0.008, 0.013)
HOUSE_FOG_DENSITY = 0.055
HOUSE_SIGN_COLOR = (32, 35, 41)  # Faint navigation labels; HUD stays unlit.
FLASHLIGHT_COLOR = (4.0, 3.78, 3.36)
FLASHLIGHT_FOV = 56
FLASHLIGHT_RANGE = 18
# Constant term limits close-up brightness; quadratic term softens distant light.
FLASHLIGHT_ATTENUATION = (3.2, 0.035, 0.025)
FLASHLIGHT_EXPONENT = 12
FLASHLIGHT_SHADOWS = True  # False is cheaper but permits light through walls.
FLASHLIGHT_SHADOW_RESOLUTION = 512

# GHOST
GHOST_PATROL_SPEED = 2.1
GHOST_INVESTIGATE_SPEED = 2.6
GHOST_CHASE_SPEED = 5.9  # Faster than walking, slower than an available sprint.
GHOST_VISION_DISTANCE = 12
GHOST_FOV = 85
GHOST_HEARING_BASE = 3
GHOST_CATCH_DISTANCE = 1.25
GHOST_LOST_SIGHT_SECONDS = 2.5
GHOST_SEARCH_SECONDS = 4.0
GHOST_ACTIVE_SEARCH_SECONDS = 14
GHOST_SEARCH_SPEED = 2.2
GHOST_DETECTION_SECONDS = 0.65
GHOST_DETECTION_DECAY = 1.2
GHOST_DARK_VISIBILITY = 0.65
GHOST_CROUCH_VISIBILITY = 0.6
GHOST_MEMORY_SECONDS = 12
GHOST_UNCERTAINTY_GROWTH = 0.6
GHOST_SEARCH_RADIUS = 5
GHOST_NOISE_COOLDOWN = 0.8
GHOST_SOUND_OCCLUSION = 0.55
GHOST_INSPECTION_SECONDS = 1.5

# ITEMS
EXIT_KEY_ID = "exit_key"

# HORROR PACING / ACCESSIBILITY (frequency 0 disables events)
HORROR_SEED = 1729
HORROR_EVENT_FREQUENCY = 1.0
HORROR_INTENSITY_LIMIT = 0.75
HORROR_INITIAL_QUIET_SECONDS = 30.0
HORROR_CHECK_SECONDS = 5.0
HORROR_COOLDOWN_SECONDS = (28.0, 48.0)
HORROR_POST_CHASE_QUIET_SECONDS = 18.0
HORROR_CATEGORY_WEIGHTS = {"lighting": 0.35, "environment": 0.40, "apparition": 0.25}
HORROR_REDUCED_FLICKER = True  # Slow, smooth dimming by default; no screen flashes.
JUMPSCARE_SECONDS = 1.8
JUMPSCARE_INTENSITY = 0.65  # 0 removes approach, shake, and darkening; catch still ends.
JUMPSCARE_REDUCED_SHAKE = False
JUMPSCARE_SHAKE_DEGREES = 0.45
LOAD_GRACE_SECONDS = 5.0
LOAD_GHOST_MIN_DISTANCE = 12.0
SAVE_COOLDOWN_SECONDS = 10.0

# User preferences are separate from level data and gameplay/save state.
import json
import math
import os
from pathlib import Path
from copy import deepcopy

BINDING_DEFAULTS = dict(forward='w', backward='s', left='a', right='d', sprint='shift',
                        crouch='control', interact='e', flashlight='f', inventory='tab',
                        use_item='u', pause='escape')
SUPPORTED_BINDINGS = set('abcdefghijklmnopqrstuvwxyz') - {'r'}
SUPPORTED_BINDINGS.update(('space','shift','control','tab','escape'))


def validate_bindings(bindings):
    if not isinstance(bindings, dict) or set(bindings) != set(BINDING_DEFAULTS):
        raise ValueError('All control actions require bindings')
    result = {}
    for action, key in bindings.items():
        if not isinstance(key, str) or key not in SUPPORTED_BINDINGS or key=='escape' and action!='pause':
            raise ValueError('Unsupported/reserved key; Escape and menu keys remain reliable')
        result[action] = key
    if len(set(result.values())) != len(result):
        raise ValueError('Conflicting key bindings')
    return result

PREFERENCES_PATH = Path(__file__).resolve().parent / "data" / "user_preferences.json"
PREFERENCE_DEFAULTS = {
    "mouse_sensitivity": 1.0,
    "brightness": 1.0,
    "shadow_quality": "low",
    "horror_frequency": HORROR_EVENT_FREQUENCY,
    "reduced_flicker": HORROR_REDUCED_FLICKER,
    "reduced_shake": JUMPSCARE_REDUCED_SHAKE,
    "jumpscare_intensity": JUMPSCARE_INTENSITY,
    "ghost_difficulty": "standard",
    "fps_cap": 0,
    "text_scale": 1.0,
    "bindings": BINDING_DEFAULTS,
}
PREFERENCE_CHOICES = {
    "mouse_sensitivity": (.25, .5, .75, 1., 1.25, 1.5, 2., 3.),
    "brightness": (.5, .75, 1., 1.25, 1.5, 2.),
    "shadow_quality": ("off", "low", "high"),
    "horror_frequency": (0., .5, 1., 1.5, 2., 3.),
    "reduced_flicker": (False, True),
    "reduced_shake": (False, True),
    "jumpscare_intensity": (0., .25, .5, .65, .8, 1.),
    "ghost_difficulty": ("relaxed", "standard", "hard"),
    "fps_cap": (0, 30, 60, 120),
    "text_scale": (1.0, 1.25, 1.5),
}
NEXT_GAME_SETTINGS = ("shadow_quality", "ghost_difficulty")
GHOST_DIFFICULTY = {"relaxed": (.85, .8), "standard": (1., 1.), "hard": (1.1, 1.2)}


def validate_preferences(values):
    """Validate a partial configuration, retaining defaults for missing fields."""
    if not isinstance(values, dict) or set(values) - set(PREFERENCE_DEFAULTS):
        raise ValueError("Unknown preference or invalid configuration")
    result = deepcopy(PREFERENCE_DEFAULTS)
    bounds = {"mouse_sensitivity": (.25, 3), "brightness": (.5, 2),
              "horror_frequency": (0, 3), "jumpscare_intensity": (0, 1)}
    for key, value in values.items():
        if key == 'bindings':
            result[key] = validate_bindings(value)
            continue
        if key == 'text_scale':
            valid = type(value) in (int,float) and value in PREFERENCE_CHOICES[key]
        elif key in bounds:
            low, high = bounds[key]
            valid = (type(value) in (int, float) and low <= value <= high and math.isfinite(value))
        elif key in ("reduced_flicker", "reduced_shake"):
            valid = type(value) is bool
        elif key == "fps_cap":
            valid = type(value) is int and value in PREFERENCE_CHOICES[key]
        else:
            valid = isinstance(value, str) and value in PREFERENCE_CHOICES[key]
        if not valid:
            raise ValueError(f"Invalid value for {key}")
        result[key] = value
    return result


class Preferences:
    """Validated, atomic local JSON preferences; never a checkpoint/save file."""
    def __init__(self, path=PREFERENCES_PATH):
        self.path = Path(path) if path is not None else None
        self.values = deepcopy(PREFERENCE_DEFAULTS)
        self.error = ""
        if self.path is not None and self.path.exists():
            try:
                document = json.loads(self.path.read_text(encoding="utf-8"))
                if document.get("version") != 1:
                    raise ValueError("Unsupported preferences version")
                self.values = validate_preferences(document["values"])
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                self.error = "Preferences could not be loaded; using defaults."

    def save(self, values):
        validated = validate_preferences(values)
        if self.path is not None:
            temporary = self.path.with_suffix(".json.tmp")
            try:
                temporary.write_text(json.dumps({"version": 1, "values": validated}, indent=2), encoding="utf-8")
                os.replace(temporary, self.path)
            finally:
                temporary.unlink(missing_ok=True)
        self.values = validated
        self.error = ""
