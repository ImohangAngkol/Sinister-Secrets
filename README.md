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

The white pickup on the foyer console is the flashlight, the blue pickup on the
kitchen counter is a battery, and the yellow pickup on the Bedroom Two bedside
table is the exit key. Unlock the brown north exit with E, then walk through
the opening to escape. The ghost uses placeholder geometry.

## Rendering and gameplay fixes

- Use `color.rgb32`/`rgba32` for 0-255 values. Ursina 8.3's `rgb`/`rgba`
  expect normalized 0-1 values; the previous values saturated the surfaces.
- Create ambient/fill lighting and use Panda3D's generated shader only for
  world geometry. Clear unlit shader overrides on room/furniture containers;
  UI retains Ursina's unlit/text shaders. Replace the inherited unset fog,
  which rendered generated lighting black, with explicit exponential fog.
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

Baseline `f1a6f2c` passed its original 13 tests before Milestone 1 changes.
Milestone 2 started from clean `main` commit `c49e6eb`, with all 25 Milestone 1
tests passing. Milestone 2 passed **39 tests**: those 25 cases plus 14
house/data checks. Milestone 2.5 started from clean `main` commit `434a24e`,
with those 39 tests passing, and adds seven lighting regressions for **46 tests**.
Map-dependent test coordinates and waypoint IDs were adapted
to the authored layout; the original movement, interaction, collision, state,
flicker and restart assertions remain. The original exit test waits for the
opening animation before expecting clearance.
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
The extended harness also captures six authored house views, using a posed
developer camera and hiding only the ceiling for the elevated overview.

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

## Milestone 2: authored haunted house

The fixed 36 x 36 unit house has 15 areas, 25 internal doorways, a four-unit-wide
central hallway, and three-unit-wide openings. Walls, floor tiles, furniture and
the ceiling use built-in geometry, normalized colors and existing lighting.
Room labels, different muted floor tones and geometric furniture provide
landmarks without imported textures, models, images or audio.

| Location | Areas and landmarks |
| --- | --- |
| South/front | Entrance foyer with flashlight console and red bench; west/east front passages |
| Centre | Main hallway with tall clock; living room with red sofa/table; Bedroom One with blue bed/wardrobe |
| West wing | Dining room with table/chairs; kitchen with counters/cabinets/battery; storage with shelves/boxes |
| East/north wing | Bedroom Two with plum bed/bedside exit key; bathroom with bath/sink |
| East/south wing | Basement vestibule; locked alcove with placeholder steps, reserved for a future milestone |
| North/rear | West/east rear passages and exit area with the functional keyed exit |

Two example evasion loops are:

- Foyer -> west front passage -> storage -> kitchen -> dining -> main hall -> foyer.
- Main hall -> Bedroom One -> basement vestibule -> east front passage -> foyer -> main hall.

Rear passages add more routes through the exit area. The basement's inner door
is sealed; the vestibule remains accessible, and completion never needs a
basement key. Interior room connections are open framed doorways. There is no
interior door-opening AI or advanced perception in this milestone.

The existing loader `game/levels/haunted_house.py` now reads and validates the
existing JSON files. House data defines rooms, furniture, connections and camera
views; navigation data defines 43 waypoints, 53 bidirectional edges and room
patrol destinations; spawn/door data defines player, ghost, pickups and locks.
Item restoration values still come from `game/data/items.json`. Wall segments
are derived from the authored room rectangles, merging shared edges and removing
only declared openings. Nothing is randomized except existing ghost patrol choice.

New validation confirms:

- Every area is reachable, and removing any single room connection still leaves
  every area connected; no single doorway is a mandatory choke point.
- All 225 ordered room pairs have A* routes. Every waypoint edge has real ghost
  clearance, and every internal doorway accepts actual controller movement.
- Spawn and waypoint positions have floor support and no immediate obstruction.
- 568 perimeter rays find collision barriers, including the closed exit seams.
- A simulated player walks to all 15 room centres without teleporting, then a
  separate controller-driven run collects the flashlight, battery and key and
  crosses the exit, without opening the basement.
- Blocking the real living/storage doorway after planning makes the ghost
  replan through the house loop and reach storage without penetrating geometry.

The native scripted performance sample on this machine measured approximately
8 ms median and 14 ms p95 per task-manager frame, with 103 colliders. This is a
short development sample, not a benchmark for ordinary laptops. Geometry has
one bounding collider per furniture assembly; decorative pieces do not each
add a collider. Lower-end GPU performance and longer sessions need manual testing.

Run the windowed smoke command above to regenerate these ignored screenshots:

| View | Screenshot |
| --- | --- |
| Entrance foyer | `game/tests/render_house_foyer.png` |
| Main hallway | `game/tests/render_house_main_hall.png` |
| Living room | `game/tests/render_house_living.png` |
| Kitchen | `game/tests/render_house_kitchen.png` |
| Bedroom Two | `game/tests/render_house_bedroom.png` |
| Elevated layout | `game/tests/render_house_overview.png` |

Milestone 2 files changed:

| Area | Files |
| --- | --- |
| Level/loading | `game/levels/haunted_house.py`, `game/levels/haunted_house.json`, `game/levels/navigation.json` |
| Spawn/doors | `game/data/spawn_points.json`, `game/data/doors.json` |
| World | `game/world/house.py`, `game/world/room.py`, `game/world/waypoint.py` |
| Scene/patrol destinations | `game/scene_manager.py`, `game/ghost/ghost.py`, `game/ghost/ghost_ai.py` |
| Verification | `game/tests/test_prototype.py`, `game/tests/windowed_smoke.py`, new `game/tests/test_level_data.py` |
| Documentation | `README.md` |

No unresolved failure remains in the tested scenarios. Human evasion/balance,
real Alt+Tab, prolonged sessions and other hardware remain unverified. Labels
and furniture are development placeholders; the overview intentionally removes
the ceiling visually. No puzzle, save, advanced inventory or audio implementation
was added, and no commits, merges or pushes were performed.

## Milestone 2.5: darkness and flashlight lighting

Ambient light is reduced to (0.10, 0.11, 0.14), with a very faint directional
fill. Nearby silhouettes remain visible; muted exponential fog (density 0.055)
reduces distant contrast. The background matches the fog. This explicitly uses
Panda3D's `Fog.set_exp_density`: Ursina 8.3's numeric `scene.fog_density` setter
does not configure exponential density.

The important rendering fix clears the default unlit shader on model-less
Room and furniture containers. Previously those containers overrode House's
generated lighting, leaving their floors and props bright and unresponsive to
the spotlight. Walls, floors, props, doors, pickups and the ghost now use the
existing generated shader. Geometry, room data and collisions are unchanged.

The existing camera-following native spotlight uses a 56-degree cone, warm light,
constant/linear/quadratic attenuation and an 18-unit shadow lens range. Its
intensity and constant attenuation are paired to reveal objects across a room
without washing out nearby gray walls. One 512 x 512 shadow map blocks direct
light behind opaque geometry. Registration stays stable; OFF, dark flicker
intervals, depleted battery and cleanup set its contribution to zero. Drain
remains 3.5 percentage points per second and flicker remains time-based. No
screen overlay, custom shader, external assets or bloom was introduced.

Lighting values are centralized in `game/settings.py`. Set `FLASHLIGHT_SHADOWS`
to `False` for a cheaper fallback, with the limitation that direct light can
then pass through walls. The default keeps shadows enabled. Shadow-map edges
can be coarse, the cone has a visible boundary on close walls, and exponential
fog is distance haze rather than a volumetric beam. The useful illumination
range is gradual, not a hard visibility boundary. World labels remain faint
unlit navigation markers; the HUD remains bright and independent of world fog.
Monitor brightness and lower-end GPU performance still need human assessment.

Seven new regressions check native activation/flicker/depletion and stable
registration, camera alignment after simulated mouse input, real shadow
occlusion, dark geometry outside the cone and distance falloff, floor/furniture
lighting, ghost/battery/key/exit illumination, and configured distance fog.
The existing visibility test now asserts intentional darkness; only the
developer palette overview uses brighter temporary lighting and no fog.

Run the native smoke harness to generate nine identical-camera OFF/ON pairs:
`render_lighting_{foyer,main_hall,living,kitchen,bedroom,ghost,battery,key,exit}_{off,on}.png`
in `game/tests`. The harness dispatches E/F through the real engine before
posing the comparison camera and freezing player/AI updates. Screenshot pairs
do not advance battery time. The elevated overview uses developer lighting.
The offscreen suite also saves real shadow, falloff, fog and subject captures.
These are real rendered images with scripted poses and inputs, not a human
playthrough. Existing native focus-handler fallback limitations still apply.

At 1280 x 720 on the NVIDIA RTX 3050 Laptop GPU, the 120-frame native samples
with frozen camera/AI measured 6.96 ms median / 8.86 ms p95 with light OFF and
7.04 ms median / 11.42 ms p95 with light ON. OFF keeps the registered shadow light
to avoid shader regeneration; this comparison does not measure shadow-map cost
against disabling shadows. Nine world-region brightness comparisons increased
when ON, and reviewed captures showed colored geometry rather than white walls.
Compilation, all 46 tests and `git diff --check` passed. Normal engine PNG-profile
and missing-icon warnings remain; no shader errors were observed.

Modified files: `game/settings.py`, `game/world/environment.py`,
`game/world/room.py`, `game/player/player.py`, `game/tests/test_prototype.py`,
`game/tests/windowed_smoke.py`, and `README.md`.

Engine references: [Panda3D lighting and shadow mapping](https://docs.panda3d.org/1.10/python/programming/render-attributes/lighting),
[generated shaders](https://docs.panda3d.org/1.10/python/programming/shaders/shader-generator),
and [exponential fog](https://docs.panda3d.org/1.10/python/programming/render-attributes/fog).

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
   it. Compare the same wall/prop/ghost with F off and on: the lit object should
   retain its color, with objects outside the cone staying dark. Aim down a long
   hallway and around a doorway; check distant haze and wall occlusion. Nearby
   silhouettes should remain faintly visible without the flashlight. Below 15%,
   observe flicker; at 0%, confirm the light turns off.
3. Reach the kitchen via living -> storage -> kitchen, or main hall -> dining ->
   kitchen. Use E on the blue counter battery while below 100%; charge increases
   by up to 35 points and the pickup vanishes.
4. Collect the yellow key on Bedroom Two's bedside table in the northeast inner
   wing, reached through the main hall or the east passages. Before collection, E on the
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
8. Walk both example loops above. Turn through successive doorways while being
   chased; check that walls break sight and the ghost follows reachable routes.
   Visit the storage, both bedrooms and bathroom; walk around furniture and
   inspect wall corners for snagging. Try E on the basement door: it must remain
   sealed and must not affect escape through the north exit.

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

## Recommendations for Milestone 3

1. Human playtest the loops, flashlight economy, spawn safety and pursuit speed;
   complete an Alt+Tab/restart soak and profile a lower-end student laptop.
2. Make SEARCH visit reachable last-seen locations and nearby rooms; improve
   short-term memory and investigation priorities with deterministic tests.
3. Tune vision/hearing occlusion and reacquisition so alternate routes reward
   movement and the ghost cannot use inaccessible target positions.
4. Add intentional interior-door handling only with navigation/recovery tests;
   keep rooms and pickups reachable if a door becomes blocked.
5. After AI is stable, scope hiding and simple puzzles as separate work, then
   inventory expansion and horror events. Imported assets, sound and saving
   remain future work requiring authorization.

Engine references: [Ursina color API](https://www.ursinaengine.org/api_reference_v8_0_0/color.html)
and [Panda3D lighting](https://docs.panda3d.org/1.10/python/programming/render-attributes/lighting).
