# Sinister Secrets

Python/Ursina first-person horror prototype.

## Controls
- W A S D - Move
- Mouse - Look
- Shift - Sprint
- E - Interact
- F - Flashlight
- R - Restart after death/win
- Esc - Quit

## Prototype 0.1
- First-person movement
- Flashlight + battery
- Key pickup
- Locked exit door
- Ghost patrol/investigate/search/chase AI
- Ghost vision + hearing
- A* waypoint navigation
- Win / lose states

Run with:

```powershell
python main.py
```

With the existing Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe main.py
```

The white pickup near spawn is the flashlight, the blue pickup is a battery,
and the yellow pickup is the exit key. Unlock the brown north exit with E,
then walk through the opening to escape. The ghost uses placeholder geometry.

## Rendering and gameplay fixes

- Use `color.rgb32`/`rgba32` for 0-255 values. Ursina 8.3's `rgb`/`rgba`
  expect normalized 0-1 values; the previous values saturated the surfaces.
- Create ambient/fill lighting and use Panda3D's generated shader only for
  world geometry. UI retains Ursina's unlit/text shaders. Disable the inherited
  default fog, which rendered the generated lighting black.
- Keep the spotlight registered and toggle its color contribution. Disabling a
  Light Entity alone does not remove its registered Panda3D light. The beam
  follows camera rotation, casts shadows, and drains battery only while on.
- Use explicit world-space Panda3D rays. Ursina 8.3's shared ray Entity could
  accumulate incorrect rotations after opposite casts. The same adapter is
  used by interaction, ghost sensing/navigation, and the existing first-person
  controller, without modifying the installed engine files.
- Substep player movement during slow frames. Ghost movement checks its width
  against colliders, validates graph edges, joins only visible waypoints, and
  keeps progressing during repeated replans. Catching requires an unobstructed
  ray to the player. Horizontal vision ignores vertical eye-height differences.
- Escape requires the key, unlocking, and crossing the doorway; merely opening
  the door no longer wins after a timer. Normalize doorway/vision directions
  because Ursina's direction vectors include Entity scale.
- Add HUD contrast panels, keep debug text within the screen, display flashlight
  ON/OFF, and update inventory text only when the displayed values change.

Existing folders, modules, level data, settings, and placeholder systems remain
in place. No external game assets were added.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s game/tests -v
.\.venv\Scripts\python.exe -m compileall -q main.py game
```

The suite uses real Ursina/Panda3D geometry, collision traversal, and GPU
rendering in an offscreen buffer. It simulates held keys and mouse velocity;
mouse capture is bypassed only in the offscreen tests because GraphicsBuffer
has no window pointer API. Selected sensor results are patched to make state
transitions deterministic; other tests exercise real vision and hearing.

Generated screenshots are written into the existing `game/tests` folder and
ignored by Git. Review `render_spawn.png`, `render_overview.png`,
`render_flashlight_off.png`, `render_flashlight_on.png`, `render_escape.png`,
and `render_caught.png`. The initial verification also captured a real windowed
launch as `render_windowed.png`.

Verified on Windows with Python 3.14.2, Ursina 8.3.0, Panda3D 1.10.16, and an
NVIDIA RTX 3050 Laptop GPU: 13 automated tests passed, screenshots were visually
reviewed, and the actual main entry point ran for 120 frames with live AI and
mouse capture. Offscreen testing required execution outside the Codex filesystem
sandbox because Panda3D could not read its installed resources inside it.

Manual keyboard/mouse gameplay, R restarting the process, prolonged play,
other GPUs/operating systems, and resized-window HUD layout remain unverified.
The engine can print harmless framebuffer, bundled PNG profile, or icon warnings.
Save, audio, menus, head bob, and paranormal events remain their original stubs.

Files changed:

| Area | Files |
| --- | --- |
| Entry point/documentation | `main.py`, `README.md`, `.gitignore` |
| World/lighting | `game/world/environment.py`, `game/world/house.py`, `game/world/door.py`, `game/world/exit_door.py`, `game/scene_manager.py` |
| Player/items | `game/player/player.py`, `game/player/interaction.py`, `game/items/item.py` |
| Ghost | `game/ghost/ghost.py`, `game/ghost/ghost_ai.py`, `game/ghost/ghost_navigation.py`, `game/ghost/ghost_vision.py` |
| HUD | `game/ui/hud.py`, `game/ui/inventory_ui.py`, `game/ui/interaction_prompt.py`, `game/ui/game_over.py` |
| Tests | `game/tests/test_inventory.py`; added `game/tests/test_prototype.py` |

Engine references: [Ursina color API](https://www.ursinaengine.org/api_reference_v8_0_0/color.html)
and [Panda3D lighting](https://docs.panda3d.org/1.10/python/programming/render-attributes/lighting).
