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
git diff --check
.\.venv\Scripts\python.exe -m game.tests.windowed_smoke
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

Baseline `f1a6f2c` passed its original 13 tests before Milestone 1 changes. The
current suite passes **25 tests**: those 13 cases plus 12 regression cases. The
original exit test now waits for the opening animation before expecting clearance.
Walking (5 units/s), sprinting (8 units/s), blocked-wall noise, corners, ghost
movement budgets, door timing, and flashlight drain/flicker are exercised with
simulated timesteps at 4, 30, 60, and 120 FPS. Movement assertions use real
colliders; some ghost sensor inputs use deterministic patches.

The native Windows smoke harness launches the actual `main.py`, checks live AI
startup and capture, resizes to 640x480, 960x720, and 1280x720, and dispatches six
scripted R restarts after alternating win/loss callbacks. The offscreen suite also
checks 12 restarts, including disposal during an opening door, stable entity,
collider, timer and light counts, and reset inventory. Native screenshots at all
three sizes and both end screens were reviewed along with the flashlight images.

These are scripted engine tests, not human keyboard/mouse playthroughs. Windows
refused the harness's request to lose foreground focus; the pause/release/resume
checks therefore used an explicit focus-handler fallback. A real Alt+Tab test
is still required. Other GPUs/operating systems, prolonged play, suspend/resume,
very narrow windows and physical pointer movement remain unverified. At 4 FPS,
brief flicker intervals can fall between displayed frames, although the elapsed
time schedule and battery consumption are consistent.

Verified with the existing Windows environment: Python 3.14.2, Ursina 8.3.0,
Panda3D 1.10.16. Offscreen/native checks required execution outside the Codex
filesystem sandbox because Panda3D could not read installed resources inside it.
No Linux virtual display is available in this Windows environment; testing used
Panda3D's offscreen buffer and the native window. The engine still prints
framebuffer, bundled PNG profile, or icon warnings, without test exceptions.
Save, audio, menus, head bob, and paranormal events remain their original stubs.

## Milestone 1: stability and AI recovery

- Measure movement noise from actual horizontal travel. Process full elapsed
  frame time with conservative controller substeps instead of discarding time
  above 0.1 seconds. Mouse displacement is applied once per rendered frame.
- Track blocked ghost movement and replan after 0.5 seconds. Validate graph
  connections against current geometry and consider alternative reachable entry
  nodes. Failed patrol, investigation or chase routing enters a four-second
  SEARCH recovery, then retries patrol. Recovery temporarily suppresses sensing
  retries. All five original AI states remain in use, with collision sweeps on
  every movement substep.
- Animate doors by elapsed time over 0.8 seconds. Keep a fixed invisible doorway
  blocker plus the rotating panel collider until opening finishes. Repeated
  interactions cannot restart opening. This deliberately allows passage only
  at completion, rather than estimating partial clearance.
- Use elapsed bright/dark intervals for low-battery flicker, carrying time
  overshoot across frames. Drain remains 3.5 percentage points per second while on.
- Keep battery pickups at full charge, display feedback, and remove them only
  after a successful refill.
- Restart within the existing game window, disposing old world entities and
  registered lights safely. Focus loss pauses gameplay and clears held input;
  focus return restores capture while playing and skips the first movement
  frame. HUD anchors and message width adapt to resize; end screens hide HUD.

Milestone 1 files changed (existing folders preserved):

| Area | Files |
| --- | --- |
| Lifecycle | `game/game_manager.py`, `game/scene_manager.py` |
| Player/items | `game/player/player.py`, `game/items/battery.py` |
| Ghost | `game/ghost/ghost_ai.py`, `game/ghost/ghost_navigation.py` |
| Doors | `game/world/door.py`, `game/world/locked_door.py`, `game/world/exit_door.py` |
| HUD | `game/ui/hud.py`, `game/ui/game_over.py` |
| Verification/documentation | `game/tests/test_prototype.py`, new `game/tests/windowed_smoke.py`, `README.md` |

## Manual verification

From PowerShell:

```powershell
Set-Location 'C:\Users\User\Desktop\Sinister_Secrets'
.\.venv\Scripts\python.exe main.py
```

1. Move with W/A/S/D and look with the mouse. Walk and Shift-sprint into the
   interior walls and outer corners; confirm no penetration or unexpected speed
   changes. Stationary wall pushing must not create new hearing-driven pursuit;
   existing visual pursuit can continue. The automated test checks noise exactly.
2. Aim at the white flashlight near spawn and press E. Toggle F; confirm the
   beam follows the camera, switching off stops drain, and switching on resumes
   it. Below 15%, observe flicker; at 0%, confirm the light turns off.
3. Reach the blue battery in the northwest room via the central opening. Use E
   while below 100%; charge increases by up to 35 points and the pickup vanishes.
4. Collect the yellow key in the southeast room. Before collection, E on the
   brown north exit reports locked. After collection, repeatedly press E during
   opening and walk against the door: the animation must continue and the
   doorway stay blocked until it finishes. Walk through to win.
5. On the win screen, press R. Confirm the same window resets spawn, inventory,
   battery and ghost. Let the ghost catch you, then press R again. Repeat both
   outcomes several times and watch for exceptions or leftover lights/objects.
6. While walking, Alt+Tab away, release the key, wait, then return. Confirm the
   cursor is available outside the game, the game paused while unfocused, and
   returning does not continue movement or jump the view. Check capture while
   playing and cursor release on win/loss screens.
7. Resize to 640x480, 960x720, and 1280x720 while playing and on end screens.
   Confirm inventory, ghost state, prompts and messages stay readable.

For a full-charge pickup check without the ghost interrupting, launch this
temporary test setup (it does not change the saved game code):

```powershell
.\.venv\Scripts\python.exe -c "from ursina import Ursina; from game.game_manager import GameManager; app=Ursina(borderless=False, fullscreen=False, editor_ui_enabled=False); gm=GameManager(); gm.scene_manager.player.stats.battery=100; gm.scene_manager.ghost.enabled=False; app.run()"
```

Pick up the flashlight, leave it off, then try E on the blue battery. It must
remain and report full charge. Switch F on, allow charge to fall, then press E
again; the refill must succeed and remove the battery.

To cap the normal game at a selected FPS, replace `4` with `30`, `60`, or `120`:

```powershell
.\.venv\Scripts\python.exe -c "from panda3d.core import loadPrcFileData; loadPrcFileData('', 'clock-mode limited\nclock-frame-rate 4'); import main"
```

Hardware may run below a requested cap. Automated fixed-timestep tests provide
the numerical speed and flicker comparisons. Dynamic blockage and alternate
route recovery are reproduced by the regression suite's temporary colliders;
the current level has no movable-obstacle gameplay mechanic.

## Development roadmap after this milestone

1. Complete human playtesting and a longer restart/focus soak; profile movement
   substeps and raycasts before increasing level complexity.
2. Improve ghost memory, reachable search locations, retry priorities, and
   reactions to changing doors, with deterministic navigation regressions.
3. Build a placeholder house/maze exploration loop with readable landmarks,
   safe spawns and complete navigation coverage; validate every passage width.
4. Add small interconnected puzzles and item use, then inventory capacity,
   inspection and persistence without allowing unwinnable progression.
5. Tune hiding, resource pressure and paranormal events. Add audio/visual assets
   only after authorization and stable gameplay, then menus, settings, saving,
   accessibility and wider hardware testing.

Engine references: [Ursina color API](https://www.ursinaengine.org/api_reference_v8_0_0/color.html)
and [Panda3D lighting](https://docs.panda3d.org/1.10/python/programming/render-attributes/lighting).
