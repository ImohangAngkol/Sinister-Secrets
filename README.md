# Sinister Secrets

Python/Ursina first-person horror prototype.

## Controls

- W A S D - Move
- Mouse - Look
- Shift - Sprint
- Hold Ctrl - Crouch (release to stand when headroom is clear)
- E - Interact / enter wardrobe / leave hiding
- F - Flashlight
- Tab - Open/close inventory; Up/Down select; Enter inspect/read
- U then Enter - Confirm use of the selected stored battery; Backspace cancels
- 0-9 / Backspace / Enter - Enter, erase, and submit a lock combination
- R - Restart after death/win or during a staged catch
- Esc - Close inventory/note/lock screen first; otherwise pause/resume. On an end screen, return to the main menu.
- Menu Up/Down or Tab - Select; Enter or mouse click - Confirm
- Settings Left/Right - Adjust; Apply and Back saves; Esc cancels
- PgUp/PgDn - Menu pages and note pages
- Controls/Rebind - Change gameplay keys; Escape always closes/cancels menus

## Prototype 0.1

- First-person movement
- Flashlight + battery
- Key pickup
- Locked exit door
- Ghost patrol/investigate/search/chase AI
- Ghost vision + hearing
- A* waypoint navigation
- Win / lose states
- Sprint stamina and crouching
- Wardrobe hiding with suspicious/witnessed ghost inspections

Run with:

```powershell
python main.py
```

With the existing Windows virtual environment:

```powershell
.\.venv\Scripts\python.exe main.py
```

The white pickup on the foyer console is the flashlight. Batteries are collected
into inventory and used deliberately. Read the living-room note to begin the
fuse, combination, and crowbar sequence below. The yellow exit key remains
inaccessible until its bedroom cabinet is opened. Unlock the brown north exit
with E, then walk through the opening to escape. The ghost uses placeholder geometry.

## Milestone 7: saves, checkpoints, accessibility, and longer sessions

Current implementation extends the existing modules and authored house. Earlier
milestone sections below retain their original test/balance history. No external
assets, new levels, puzzle changes, commits, pushes, or merges were added.
Inspection began on clean `main`, commit `e1fe822`, in
`C:\Users\User\Desktop\Sinister_Secrets`. Python 3.14.2, Ursina 8.3.0 and
Panda3D 1.10.16 were used for validation.

### Local save format and reliability

`game/systems/save_manager.py` now implements schema **version 1**. Paths resolve
relative to the project, independent of the working directory:

- `game/data/manual_save.json`: the single manual slot.
- `game/data/checkpoint_save.json`: the separate milestone snapshot.
- `game/data/user_preferences.json`: preferences only; never gameplay progress.

Gameplay saves and their `.json.tmp` files are Git-ignored. The existing data
directory is reused. JSON stores version, level ID, UTC timestamp, run UUID,
slot, and checkpoint milestone when applicable. Player, inventory, progression,
and world sections contain only data; no entities, callbacks, shaders or object
references are serialized. Pickups/doors use the level's existing stable IDs.

Typed validation checks critical fields, finite numeric ranges, unique item
quantities, collected IDs, retained notes, consumed fuse/battery accounting,
puzzle dependencies, key-gated pickups, basement/exit doors, and the checkpoint
milestone/foyer position. Missing optional camera/crouch/exhaustion fields get
safe defaults; missing critical state, duplicate JSON keys, invalid UTF-8,
non-finite numbers, files over 64 KiB and incompatible versions are rejected.
Missing files simply disable Continue. Diagnostics are logged and UI failures
are shown without crashing or reporting premature success.

Writes validate first, flush/fsync a sibling temporary JSON file, and replace
with `os.replace`; failed writes preserve the previous slot and clean the temp.
Invalid existing slots are **preserved and never silently overwritten**. To
recover such a slot, manually back up/rename the indicated JSON file before
saving again. Do not edit the only copy of valid progress for testing.

Loading validates before rebuilding, restores into a staged fresh scene,
checks the saved body position against that scene's actual colliders, then swaps
sessions. A failure preserves the outgoing player/HUD/camera/fog/lights and
cleans staged entities, including a constructor that raises before returning.
Geometry-invalid saves can pass JSON validation and enable Continue, but are
rejected at staging with feedback. No migration from future/incompatible schema
versions is attempted.

### Menus, saving, checkpoints, and exact state

Main menu: **New Game, Continue Game, Settings, Controls, Quit Game**.
Continue uses a valid manual slot first, then a valid checkpoint fallback.
It is disabled when neither slot validates. New Game requests confirmation if
any slot exists, including an invalid slot; Cancel preserves both. Confirm
creates a fresh run and clears only its old checkpoint. Manual progress remains
available until the next successful manual Save; invalid manual files still
require the explicit backup/removal described above. Restart/R creates fresh
in-memory progress without deleting the manual slot. A prior run's checkpoint
cannot appear as a Retry for the new run because the UUID must match.

Pause has **Save Game**. Saving requires ordinary safe exploration: no active
CHASE/JUMPSCARE, substantial detection, ghost within 3 units, hiding, modal,
door animation, terminal screen, or menu transition. A monotonic 10-second
cooldown prevents repeated writes. Feedback stays on Pause; success appears
only after atomic replacement succeeds. No quicksave key was added.

Automatic checkpoints follow power restoration, opening the lockbox, and
collecting the exit key. Unsafe milestones wait until exploration is safe and
the ghost is at least 12 units from the foyer. The foyer must pass actual body
clearance and support tests. If several milestones are pending, the newest
completed one is recorded once; checkpoints never replay or bypass puzzles.
IO failure produces feedback and avoids per-frame retries/log spam; it retries
at a later milestone, or the player can use manual Save.

Death offers **Retry from Checkpoint** for a valid checkpoint in the current run,
plus Restart and Main Menu. Respawn uses the clear authored foyer, facing into
the house. Battery/stamina/stored batteries are restored **exactly from the
snapshot**, with no minimum refill. Resources remain finite.

| Restored persistent state | Fresh/reset transient state |
| --- | --- |
| Manual position, player yaw, camera pitch/local rotation; crouch and camera height | Hidden/wardrobe occupant state, held keys, mouse velocity, current modal/page |
| Flashlight possession, on/off and charge; stamina, exhaustion and regeneration delay | Ghost PATROL, valid graph/route, detection/memory/hearing/search/inspection reset |
| Item quantities, notes readable from level definitions, consumed fuse/batteries | Ghost placed at a clear distant room waypoint (at least 12 units); 5-second capture/perception grace |
| Three puzzle flags, gated pickups, collected IDs, reward quantities | New seeded paranormal director, tension zero, initial quiet cooldown, no active effects |
| Open exit door; basement remains locked | Pending HUD callbacks, jumpscare proxies/overlays, noise pulses and animation timers |
| Objective derived from restored authoritative progress; no health system exists | Preferences remain separate and govern the rebuilt session |

The grace interval, minimum ghost distance and save cooldown are configurable
in `game/settings.py`. Existing five-state AI, wall sweeps, perception, hiding,
stamina, flashlight shader/beam/shadows and the puzzle chain remain intact.

### Resource balance and accessibility

| Parameter | Before | Milestone 7 |
| --- | --- | --- |
| Maximum flashlight charge | 100 | 100 |
| Starting charge | 65 | 65 |
| One kitchen battery | 35 | 35 |
| Drain, charge/second while ON | 3.5 | 0.25 |
| Starting continuous illumination | 18.6 seconds | 260 seconds (4m20s) |
| Total authored supply if not wasted | 28.6 seconds | 400 seconds (6m40s) |

Supply placement/quantity, beam appearance and stamina/difficulty defaults were
kept. Dark nearby silhouettes remain available at zero charge; required puzzles
have no battery prerequisite. Turn the light off when safe and keep/use the
stored battery when charge is low enough to avoid wasting capacity. A known
route is not a first-time human exploration benchmark; the measured route and
remaining human balance work are reported below.

Standard player walk/sprint remain 5/8 units per second versus ghost patrol/chase
2.1/5.9; full sprint drains in about 4.55 seconds (22/s), regenerates at 15/s
after 1 second, and requires 25 stamina to recover from exhaustion. Detection
baseline 0.65s, lost-sight interval 2.5s, active search 14s and wardrobe suspicion
penalties remain unchanged. Relaxed/Standard/Hard multipliers are preserved.
Existing live AI and loop/occlusion/hiding regressions provide scripted evidence;
human chase fairness and low-end laptop tuning remain necessary.

Controls/Rebind supports all 11 gameplay actions: four movement directions,
sprint, crouch, interact, flashlight, inventory, selected item use and pause.
Select an action, press Enter/click, then press a new key. Conflicts are rejected
without changing preferences; Escape cancels capture, and Reset to Defaults
restores the original keys. Changes persist atomically with preferences and
update the control list, HUD prompts and inventory shortcuts. Supported keys
are A-Z except R, plus Space, Shift, Control and Tab; Escape can bind only Pause
and always remains an emergency menu close/pause key. R, arrows, Enter,
Backspace, digits and page keys are reserved so terminal restart, menu navigation
and combination entry remain reliable. Mouse look is unchanged.

UI text sizes are **100%, 125%, 150%**, saved with preferences and applied live
to menus, HUD, objectives, inventory, notes, combination, and terminal screens.
Settings/Controls paginate with PgUp/PgDn (Up/Down still reaches every action).
Long notes paginate without losing their contents. At larger sizes resource HUD
uses extra lines during exploration and a compact two-line survival readout
above active modals, preventing overlap with their titles. Layout fitting and
message positioning handle 640x480, 960x720 and 1280x720. Reduced Flicker applies
to horror and low-battery light: below 15% it gives a steady 75% beam rather than
rapid intermittent darkness; ordinary timed flicker remains available when Off.
Drain/depletion and shadow geometry are unchanged by this preference.

### Validation and evidence

**Final full suite: 175 tests passed in 202.228 seconds**, including all 135
original tests and 40 new cases (17 JSON/IO, 19 real-engine persistence/control/
accessibility, 4 preference regressions). Compilation and `git diff --check`
passed. Test-name comparison against `HEAD` found no removed original cases.
Existing menu row assertions and battery depletion values were updated for the
new rows/drain; the original timed-flicker branch is still explicitly tested.

Native scripted validation passed two complete puzzle/save/Continue/live-catch/
checkpoint-Retry/key-save/Continue/escape routes, six terminal R restarts, and
the New Game confirmation/reset. Both routes together used **55.60 seconds of
walking simulation** (about 27.8 seconds per known route), excluding human clue
reading, searching, detours, interfaces and evasion. The old 28.6-second total
supply barely covered known-route walking; 400 seconds now leaves roughly six
additional illuminated minutes for those activities. This is a provisional
resource budget, not a measured first-time human completion time.

All nine stationary OFF/ON pairs passed pixel checks; hall means were 7.26/13.74,
ghost 9.88/23.31 and key 10.09/34.80 (0-255 RGB channel means in a cropped world
region). Room/prop colors and beam/shadow rendering remained intact. Screenshots
were visually reviewed. Review found HUD/title overlap at 150%; compacting the
modal resource readout fixed it, and a subsequent native accessibility run
recaptured all three sizes at all three scales. Native focus requests were
refused by Windows; direct focus events passed, so physical Alt+Tab remains
untested. Existing non-fatal engine warnings include the missing packaged
`textures/ursina.ico`, monitor/framebuffer notices, and PNG profile metadata;
no shader errors or unexpected gameplay exceptions occurred in the successful
native run.

On NVIDIA RTX 3050 Laptop GPU, the native initial live fixture measured median
**12.25 ms**, p95 **29.20 ms** per task step. Stationary hallway lighting ON
measured median 8.17 ms / p95 10.57 ms; OFF 9.51 / 16.62 ms. Scheduling/driver
noise means the OFF/ON numbers should not be interpreted as a lighting speedup.
Frozen-ghost horror fixtures with explicit extra rendering measured median
22.31 ms active / 21.87 ms quiet. These are scoped scripted observations, not
performance guarantees for ordinary student laptops.

| Profile snapshot | After 5 warm loads | After 25 loads | After 600 simulated seconds |
| --- | ---: | ---: | ---: |
| Live entities / colliders | 456 / 145 | 456 / 145 | 456 / 145 |
| Ghost / manager / lights / engine tasks | 1 / 1 / 3 / 9 | 1 / 1 / 3 / 9 | 1 / 1 / 3 / 9 |
| Active sequences | 1 | 1 | 0 (message expired) |
| Python traced bytes after GC | 847,252 | 893,195 | 966,710 |
| Process private bytes | 258,072,576 | 275,525,632 | 268,193,792 |
| Process working-set bytes | 246,734,848 | 271,024,128 | 271,425,536 |

The 600-second simulation measured median 186.66 ms, p95 235.12 ms and maximum
344.22 ms per profiling frame; Python traced peak 1,734,975 bytes. Each frame
advances 0.5 seconds through the unchanged 1/240 player substeps, with tracemalloc
and explicit extra rendering enabled. It is a stress workload rather than
ordinary gameplay FPS. Counts stayed stable, but heap/process deltas remain
reported; this does not establish that every multi-hour leak is absent.

The native harness calls actual `main.py` and uses temporary slots
and memory-only preferences, preserving local user data. Routes use real W
movement, collision rays, E interactions, and keyboard puzzle/menu dispatch.
The ghost is frozen for deterministic route and UI/render/profiling fixtures;
a live CHASE/inspection/capture runs for the actual death/retry checks. This is
**scripted native testing, not human interactive gameplay**.

Commands from the project root:

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py game
.\.venv\Scripts\python.exe -m unittest discover -s game/tests -v
.\.venv\Scripts\python.exe -u -m game.tests.windowed_smoke
.\.venv\Scripts\python.exe -u -m game.tests.windowed_smoke --accessibility-only
git diff --check
```

Generated `game/tests/render_*.png` files are local verification artifacts,
not game assets. `render_persistence_profile.json` contains entity/collider/
light/task/sequence counts, Python traced heap, Windows process private/working
memory, and frame distributions. Profiling compares after five warm loads and
after 25 loads plus 25 pause cycles, then advances 600 simulated seconds with
the real player/director in a native window. Tracemalloc and 0.5-second timestep
substeps add overhead; those costs are not ordinary gameplay FPS. Memory deltas
can include caches/driver allocations; stable object counts do not prove the
absence of every leak.

Representative screenshot links (generated by the commands above):

- [Continue](game/tests/render_persistence_continue_power.png), [Save feedback](game/tests/render_persistence_save_power.png).
- [Checkpoint Retry](game/tests/render_persistence_checkpoint_retry.png), [Recovered foyer](game/tests/render_persistence_checkpoint_restored.png).
- [Restored powered box](game/tests/render_persistence_restored_power.png), [Restored key progress](game/tests/render_persistence_restored_key.png).
- [Rebinding](game/tests/render_persistence_rebind.png), [Conflict feedback](game/tests/render_persistence_rebind_conflict.png).
- [150% settings at 640x480](game/tests/render_access_settings_1.5_640x480_p2.png), [150% note](game/tests/render_access_note_1.5_640x480.png), [150% inventory](game/tests/render_access_inventory_1.5_640x480.png), [150% combination](game/tests/render_access_combination_1.5_640x480.png).
- [Hall OFF](game/tests/render_lighting_main_hall_off.png), [Hall ON](game/tests/render_lighting_main_hall_on.png).

### Manual Milestone 7 acceptance route

```powershell
Set-Location 'C:\Users\User\Desktop\Sinister_Secrets'
.\.venv\Scripts\python.exe main.py
```

1. Select New Game. If saves exist, Cancel first to confirm preservation, then
   New Game/Confirm. The checkpoint resets; manual progress remains until Save.
2. E on the white foyer flashlight, F to toggle; walk/look/sprint/crouch and
   collide with walls. Test both house loops and a wardrobe during a chase.
3. Read the living-room note, close Escape; collect the fuse in storage and
   use E on the kitchen electrical box. Expect the power checkpoint when safe.
4. Pause with Escape, select Save Game, confirm success; attempt an immediate
   second save and check the cooldown. CHASE/hiding/modals must reject saving.
5. Select Return to Main Menu, Continue. Verify location/view, flashlight
   charge/on state, note/inventory, installed fuse, gated drawer and objective.
6. Collect/use the kitchen battery through Tab, select battery, U then Enter.
   At full charge it stays stored. Read the newly available kitchen tally note.
7. Use the dining lockbox: try an incorrect code, then the clue solution
   **2417**. Confirm exactly one crowbar and a lockbox checkpoint when safe.
8. Let the live ghost catch you. Watch the staged catch, choose Retry from
   Checkpoint. Verify foyer clearance, safe ghost patrol/grace, puzzle progress,
   readable notes and exact checkpoint resources; no extra crowbar should appear.
9. Reach Bedroom Two, use E on the boards, then collect its exit key. Expect
   the key checkpoint and the north-exit objective.
10. Wait 10 seconds after the prior manual save if needed; Pause/Save, return
    to menu, Continue. Verify the boards stay removed and only one key exists.
11. Reach the north exit, E to unlock; push against it while opening, then walk
    through once the 0.8-second animation completes. Confirm victory.
12. Escape to Main Menu, New Game/Confirm; verify empty inventory, initial
    flashlight pickup, all puzzles locked, no valid Retry for the previous run.
    Repeat R after death/victory and several saves/loads; watch for exceptions.
13. Settings: choose 150% text on its second page and Apply. Resize to all three
    sizes; open notes (PgDn for subsequent pages), inventory, combination,
    Controls and Pause. Check titles, footers, objective and messages for overlap.
14. Rebind movement/interact/light/inventory/use/pause, test a conflict and
    cancel, then restore defaults. Restart the application to check persistence.
    Alt+Tab while moving, release keys outside, return; check pause/capture and
    no stuck movement. Test low battery with Reduced Flicker On and Off.
15. For corrupt/version tests, use the isolated automated suite or a separate
    copy of the project with separate save files. Confirm disabled Continue or
    valid checkpoint fallback, clear failure feedback and preservation of bytes.

Remaining acceptance work: human first-time resource/chase fairness, physical
mouse/Alt+Tab and rebinding comfort, multi-hour sessions, power-loss/storage
faults beyond simulated failed writes, other GPUs/drivers and student laptops.
Only schema 1 and one authored level are supported. Cloud saves and multiple profiles are outside this milestone.

### Files and Milestone 8 recommendations

Modified existing files: `.gitignore`, `README.md`, `game/game_manager.py`,
`game/settings.py`, `game/ghost/ghost_ai.py`, `game/player/player.py`,
`game/systems/save_manager.py`, `game/systems/progression.py`,
`game/ui/main_menu.py`, `game/ui/pause_menu.py`, `game/ui/game_over.py`,
`game/ui/hud.py`, `game/ui/inventory_ui.py`, `game/tests/test_prototype.py`,
`game/tests/test_settings.py`, `game/tests/windowed_smoke.py`.
Created source file: `game/tests/test_save.py`. Existing folder structure,
level data and assets remain unchanged. Screenshots/profile JSON are ignored
local evidence files.

For Milestone 8, prioritize human balance/low-end performance measurements,
clearer clue/objective onboarding without changing puzzle dependencies, and
fault-tolerant save evolution (migration/backups with explicit retention rules).
Then design an authored next progression chapter and test its navigation/save
IDs before discussing new horror assets/audio. Avoid expanding systems before
first-time playtests establish that the current chase/resource loop is fair.

## Milestone 6: menus, pause, preferences, and lifecycle

Launch now displays **Start Game, Settings, Controls, Quit Game**. No house,
player, ghost, resource timers, or paranormal director exists before Start Game.
Escape during gameplay opens **Resume, Settings, Restart Game, Return to Main
Menu, Quit Game**. An open inventory/note/combination screen consumes Escape
first; its existing gameplay-continues policy is preserved. Inventory keeps the
mouse captured; menus release it. End screens offer Restart and Main Menu,
with R and Escape shortcuts. Escape on the main menu does not quit.

Pause uses Ursina's application pause flag, freezing entity updates, input, door
animations, resource/hiding timers, horror events, and timed HUD callbacks.
Focus suspension is independent of the current menu: regaining focus cannot
resume an already paused session or close settings. Resume clears held keys and
mouse velocity and discards the first frame's delta. The HUD callback remains
paused until after Ursina's sequence-before-entity update pass, preventing it
from expiring on that first frame. Restart and returning to the main menu use
the existing scene cleanup, removing lights, temporary effects, cinematic
geometry, and actors. New games reset inventory, puzzle gates, ghost memory,
hiding state, and seeded event pacing.

### Settings and local persistence

Use Up/Down to select; Left/Right or Enter/click changes a value. Apply and Back
validates and saves; Escape or Cancel discards edits. Preferences are stored
atomically in `game/data/user_preferences.json`, ignored by Git. The path is
resolved relative to the project, independent of the working directory. The
file stores preferences only, with no save/checkpoint or progress. Missing files
use defaults. Corrupt, incompatible, or invalid files use defaults and display
a settings warning without overwriting the file. Failed writes leave settings
open and preserve the last configuration. Tests use temporary or memory-only
preferences and do not overwrite a player's preferences.

| Setting | Default and choices | Application |
| --- | --- | --- |
| Mouse sensitivity | 1x; 0.25-3x | Current session; scales the original 40/40 sensitivity |
| Visibility brightness | 1x; 0.5-2x | Current session; scales ambient/fill, preserving beam intensity, fog, and shaders |
| Flashlight shadows * | Low/512; Off, Low/512, High/1024 | Next new game or Restart; Off permits light through walls |
| Horror frequency | 1x; 0, 0.5, 1, 1.5, 2, 3 | Current session; 0 disables events; remaining schedule is rescaled safely |
| Reduced horror flicker | On; On/Off | Current session; smooth paranormal dimming; battery flicker retains its existing time-based behavior |
| Reduced camera shake | Off; On/Off | Next catch in the current session; reduces shake to 15% |
| Jumpscare intensity | 0.65; 0-1 | Next catch; 0 removes approach/shake/darkening but still ends the caught game |
| Ghost difficulty * | Standard; Relaxed, Standard, Hard | Next new game; speed/detection multipliers 0.85/0.8, 1/1, 1.1/1.2 |
| FPS cap | Unlimited; Unlimited, 30, 60, 120 | Immediately; Panda's limited clock, subject to GPU load/vsync |

The two next-game settings are marked with an asterisk. Settings displays a
pending-change notice when the current session still uses older shadow/difficulty
values. No ghost sight, collision, route-recovery, or five-state behavior is
replaced. Applying visibility/accessibility changes restores an active paranormal
effect before applying the new light values.

### UI and balance review

Main/pause/settings/controls/end screens share dark panels, muted highlights,
spacing, and keyboard selection. End screens include clickable actions.
Inventory/puzzle text uses the same palette. Modal panels hide the ordinary
objective/startup message; new warnings appear below the panel instead of
covering item or puzzle text. Native screenshots cover all six requested UI
screens at 640x480, 960x720, and 1280x720.

Existing balance defaults are unchanged. All base values remain in
`game/settings.py`; the menu adds session difficulty and horror/accessibility
choices. At 3.5 charge/second, initial 65 charge plus the one 35-charge battery
provides **about 28.6 seconds total illumination**, requiring deliberate flashlight
use. A full sprint lasts about **4.55 seconds** (100/22), with approximately
**7.67 seconds** recovery from empty (1-second delay plus 100/15). Standard ghost
patrol/chase remains 2.1/5.9 units/second versus player walk/sprint 5/8. Hiding
retains its 12-second quiet period and 3-second breathing pulses. Horror pacing
retains its 30-second initial quiet period and 28-48-second cooldown at 1x; the
catch remains 1.8 seconds at 0.65 intensity. Human flashlight-supply and pursuit
balance testing is required before changing these defaults.

### Validation and evidence

Commands from the project root:

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py game
.\.venv\Scripts\python.exe -m unittest discover -s game/tests -v
.\.venv\Scripts\python.exe -m game.tests.windowed_smoke
git diff --check
```

The clean `main` baseline `0935e05` passed its 109 tests before changes.
All 109 test methods are retained; their shared fixture explicitly starts a
session after the new launch menu and consumes its first frame. Milestone 6
adds 20 real-engine regressions and 6 temporary-file preferences tests, covering
menu input, single-session creation, pause-safe simulation and callbacks,
focus/cursor transitions, setting validation/application/persistence failures,
new-game/restart/effect cleanup, resizing, progression preservation, collision
sweeps at each difficulty, modal warnings, clock limiting, and Quit dispatch.

Final validation: **135 tests passed in 132.930 seconds** (109 preserved plus
26 new); compilation and `git diff --check` passed. Native screenshot inspection
confirmed readable panels at all three sizes and the corrected modal HUD layout.
On this RTX 3050 Laptop GPU, startup gameplay task stepping measured 6.95 ms
median / 11.09 ms p95. With flashlight on and ghost frozen, cabinet-event checks
including an explicit second render measured 15.60 / 20.16 ms; quiet checks
15.07 / 21.44 ms. These are scripted measurements, not low-spec benchmarks.
All 75 original settings constants remain unchanged.

Modified existing files: `.gitignore`, `README.md`, `main.py`,
`game/game_manager.py`, `game/settings.py`, `game/ghost/ghost_ai.py`,
`game/ghost/jumpscare.py`, `game/systems/horror_manager.py`,
`game/ui/main_menu.py`, `game/ui/pause_menu.py`, `game/ui/game_over.py`,
`game/ui/hud.py`, `game/ui/inventory_ui.py`, `game/tests/test_prototype.py`,
`game/tests/windowed_smoke.py`. Created: `game/tests/test_settings.py`.
No existing folders/modules were renamed or removed; no assets or levels added.

The native harness runs actual `main.py`, injects engine keyboard input, and
moves the native pointer to test the menu's actual mouse ray. It checks all
requested resolutions, menu/pause/settings/inventory/end transitions, six R
restarts, live wardrobe inspection/catch, and **two full puzzle escapes separated
by victory -> main menu -> new game**, with a pause after fuse installation.
The ghost is disabled only for deterministic puzzle traversal and visual
fixtures; live sensing/inspection/catch is checked separately. This is scripted
verification, not a human playthrough. Preferences persistence is tested using
actual temporary files; the native fixture uses memory-only defaults.

Generated evidence (ignored screenshots, not imported game assets):

- [Main menu](game/tests/render_menu_main_1280x720.png)
- [Pause](game/tests/render_menu_pause_1280x720.png)
- [Settings](game/tests/render_menu_settings_1280x720.png)
- [Controls](game/tests/render_menu_controls_1280x720.png)
- [Inventory](game/tests/render_menu_inventory_1280x720.png)
- [Game over](game/tests/render_menu_game_over_1280x720.png)
- Compact and intermediate variants use `_640x480.png` / `_960x720.png`.
- Existing `render_progression_*`, `render_horror_*`, `render_lighting_*` and
  house overview evidence are refreshed by the native run.

Windows supplies a native GPU window/offscreen buffer; no Xvfb display is used.
Physical Alt-Tab still needs manual testing: the window manager refused the
programmatic focus-loss request, so the harness reports and uses a direct focus
callback fallback, then pins focus for deterministic input. Missing bundled
Ursina icon/PNG profile/framebuffer warnings are nonfatal; no external icon or
assets are added. Long-session memory profiling and low-spec hardware testing
remain unverified. Disabling flashlight shadows retains the documented light
leak approximation; reduced horror flicker does not remove low-battery flicker.

### Manual acceptance checks and Milestone 7

1. Run `.\.venv\Scripts\python.exe main.py`. Verify the launch menu and visible
   cursor; leave it open for a minute. Open Controls and Settings using mouse and
   arrows/Enter. Escape returns without quitting or applying edits.
2. Change sensitivity/brightness, choose Apply and Back, quit/relaunch and check
   persistence. Shadow/difficulty changes should remain pending in an existing
   paused session until Restart/New Game. Try FPS caps and visibility choices.
3. Start Game. Check WASD/look/Shift/Ctrl/collisions and E/F flashlight pickup and
   toggle. With the beam on, pause for 30 seconds: battery/stamina, ghost, door
   animation and horror effects must not advance. Resume with no movement jump.
4. Open Tab inventory or a note/combination interface. Escape closes it; the next
   Escape pauses. Readability should hold at 640x480, 960x720, and 1280x720.
   Alt-Tab while playing, paused, and editing settings; refocus must retain the
   state, release/capture the pointer appropriately, and clear held movement.
5. Complete the existing clue chain: living-room note -> storage fuse -> kitchen
   fuse box -> kitchen tally -> dining lockbox -> bedroom boards -> exit key -> E on
   north exit -> walk through. Battery use remains U then Enter in inventory.
   Keep the ghost active for this human challenge and test alternate routes.
6. After victory choose Main Menu, then Start Game and repeat. Seek a legitimate
   ghost catch; R should restart during/after it. Test Pause -> Restart and Pause
   -> Return to Main Menu -> Start. Check fresh items/puzzles, one ghost, and no
   remaining dimming, apparition, cinematic overlay, or unexpected input.
7. Test Quit from both menus. Report hardware, settings, battery usage, deaths,
   puzzle completion times, and any visual/input issues.

For Milestone 7, prioritize human balance measurements (especially battery
supply), longer repeated-session profiling and low-spec shadow performance,
control rebinding/text scaling and broader flicker accessibility, then approved
sound/asset integration and additional authored story content. Checkpoints
should follow an explicit persistence design; none are implemented here.

## Milestone 5: paranormal events and staged catches

The existing house, puzzle sequence, ghost sensing/navigation, controller, and
flashlight configuration are preserved. `HorrorManager` now owns a private seeded
RNG, a lightweight tension director, and at most one reversible effect. There
are no new lights, colliders, tasks, delayed event callbacks, assets, or levels.

| Category | Events | Implementation |
| --- | --- | --- |
| Lighting | `room_dimming`, `hallway_dim` | Smooth temporary tint reduction on existing room meshes/shared wall segments |
| Lighting | `power_dip`, `fill_failure` | Temporarily reduce existing ambient/fill lights; fill can briefly reach zero while ambient remains |
| Environment | `prop_shift`, `prop_vibration` | Small offsets/rotations of nonessential decorative furniture meshes; assembly colliders stay fixed |
| Environment | `cabinet_creak`, `distant_close` | A temporary decorative leaf on the living-room cabinet; closing is eligible shortly after entering |
| Apparition | `apparition`, `shadow_pass` | Faint, flat, faceless geometric silhouettes in visible corridors/doorways; shadow pass briefly moves sideways |

Effects last 3–6 seconds and restore exact original colors/transforms or destroy
temporary geometry. Silhouettes have no collider or AI, cannot hurt the player,
and disappear when approached within 2.5 units, illuminated by the real beam
with clear sight, or expired. Their thin gray shape differs from the blue solid
ghost. They use a faint unlit tint so that an apparition remains perceptible in
the dark; this adds no environmental illumination. The real ghost is never
teleported for these events.

The house has no individual powered room lamps. Local lighting disturbances are
therefore a material-tint approximation; shared wall segments may affect the
neighboring room's wall too. Global fluctuations change the actual existing
environmental lights. Neither approach changes flashlight intensity, beam,
shadows, fog, battery behavior, or registered light count. Even a fill-light
failure retains dim ambient navigation visibility. No full-screen flash is used.
Cabinet motion is decorative: exit/basement doors, their 0.8-second animation,
locks, and doorway blockers remain under gameplay control.

### Pacing and protections

Default pacing begins with 30 seconds of quiet. Every 5 seconds, an eligible
event has a probability of `0.18 + 0.32 * tension`. Completed or cancelled events
start a seeded 28–48 second cooldown. One active effect prevents overlap.
Category weights are lighting 35%, environment 40%, apparition 25%, redistributed
among eligible kinds; these weights are configurable. Selection respects the
current room, safe props, clear sight, minimum tension, and recent room entry.

Tension changes smoothly from exploration time, ghost proximity, recent chase,
puzzle progress, recent hiding, and time since an event. It influences probability
and intensity, with a 0.75 intensity cap. Leaving a chase grants at least 18
seconds without disturbances; leaving hiding grants 8 seconds. Hiding and active
chases suppress all environmental events. Early events are weaker; later
progress permits apparitions and fill failures.

Events cannot start during inventory/notes/combination screens, within 3 units
of an active puzzle prop, during exit opening, after victory/loss, or during a
staged catch. Opening an interface immediately restores an existing event.
Nearby puzzle interactions cancel effects on the next director update. The
ghost continues during interfaces according to Milestone 4's active policy;
event suppression does not grant immunity to legitimate ghost capture.

The director ticks at 30 Hz using accumulated elapsed time, with a private RNG
independent of flashlight flicker and AI randomness. Identical seeds and player/
ghost context produce the same scheduling trace at 4, 30, 60, and 120 FPS.
This does not make the entire game deterministic: player decisions and the
existing independently randomized ghost affect eligibility. History is capped
at 64 records; restart resets clock, RNG, tension, and all temporary state.

### Staged jumpscare and accessibility

Existing AI catches still require chase proximity plus line of sight, or a
completed reachable wardrobe inspection. A validated catch changes the manager
to `jumpscare`, closes interfaces, restores/cancels environmental events, freezes
normal player/ghost updates, clears navigation and held input, and hides the HUD.

Over 1.8 seconds the sequence seizes the view, smoothly brings a cube ghost
presentation closer, applies restrained camera rotation, and fades darker before
the existing CAUGHT screen. A camera-space presentation mesh is composited over
world geometry so that a wardrobe face cannot hide it. This mesh has no collider,
uses no extra light, and remains beyond the near plane. The real ghost stays at
its catch location. There is no full-screen flashing or external animation.
The controller triggers once, cleans up its mesh/overlay, and restores the
camera transform/FOV. R also restarts during the encounter. Focus loss pauses
its elapsed time, and the first refocused frame has zero dt as before.

Edit the existing `game/settings.py` constants (no settings menu yet):

| Setting | Default | Purpose |
| --- | --- | --- |
| `HORROR_SEED` | `1729` | Reproducible event RNG |
| `HORROR_EVENT_FREQUENCY` | `1.0` | 0 disables events; up to 3 scales quiet/check/cooldown intervals |
| `HORROR_INTENSITY_LIMIT` | `0.75` | Upper bound on effect strength |
| `HORROR_REDUCED_FLICKER` | `True` | Slow smooth dimming; False permits low-contrast 0.8 Hz modulation |
| `JUMPSCARE_SECONDS` | `1.8` | Encounter duration |
| `JUMPSCARE_INTENSITY` | `0.65` | 0 disables approach/shake/darkening while retaining the terminal transition |
| `JUMPSCARE_REDUCED_SHAKE` | `False` | Reduce rotation shake to 15% |
| `JUMPSCARE_SHAKE_DEGREES` | `0.45` | Base rotation amplitude, further scaled by intensity |

The reduced-flicker setting covers environmental events; the established
flashlight's low-battery flicker is unchanged.

### Verification and manual testing

Baseline validation passed all 88 tests before edits. The expanded suite passed
**109 tests in 117.110 seconds**, retaining those 88 named cases and adding 21
horror regressions. Compilation and Git diff checks passed. Legacy catch tests now wait
for the cinematic to finish before checking the terminal screen. New coverage
includes cooldowns, seeded/FPS schedules, eligibility, exact light/prop restoration,
apparition expiry/beam/approach, navigation and inventory preservation, 60 effect
cycles, 12 restarts during active events/catches, accessibility/focus, staged
transitions, duplicate prevention, a real wardrobe screenshot regression, and
the complete walking puzzle-to-escape route with a live director.

Run the same compilation, unittest, Git diff, and native smoke commands listed
in Milestone 4. Native screenshots are test evidence, not imported game assets:
[normal hallway](game/tests/render_horror_hallway_normal.png),
[lighting disturbance](game/tests/render_horror_lighting_disturbance.png),
[apparition](game/tests/render_horror_apparition.png),
[cabinet disturbance](game/tests/render_horror_environment.png),
[staged encounter](game/tests/render_horror_jumpscare.png),
[game over](game/tests/render_horror_game_over.png).

Automated scheduling tests check the ordinary seeded director separately. The
native script forces eligible events for visual fixtures, exercises a live
witnessed inspection/catch, and completes the puzzle route with the ordinary
director active. The ghost is disabled
only for deterministic puzzle routing and frozen for visual fixtures. Windows
has no Xvfb executable here: regression rendering uses an actual offscreen GPU
buffer, and `main.py` is tested in a native window. Native resize requests are
awaited; after separate native/direct focus checks, fixtures pin focus to avoid
WM changes interrupting synthetic keys. This is scripted testing, not human
gameplay or a verified physical Alt-Tab test.

At native 1280×720 on the RTX 3050 Laptop GPU, startup task timing was 7.98 ms
median / 10.94 ms p95. A matched fixed-dt fixture with flashlight ON and ghost
frozen measured 18.53 / 24.21 ms quiet versus 19.32 / 26.44 ms during cabinet
motion. Those two fixtures include an extra explicit `renderFrame`; they are
comparable to each other, not to the startup task-only measurement. Hallway
world-region mean brightness changed from 9.42 to 5.83 during the forced dip;
original colors restored exactly. Nine baseline flashlight OFF/ON comparisons
passed. These are local scripted observations, not a general hardware benchmark.

1. Run `.\.venv\Scripts\python.exe main.py`. Collect the flashlight and explore
   rooms for at least a minute; events are probabilistic, with initial quiet and
   cooldowns, so they need not appear immediately.
2. Watch the hallway with F off, then use the beam. Check that local/global
   dimming ends cleanly and that beam brightness/drain remain familiar.
3. Inspect living-room cabinet/props during a disturbance. Check movement,
   collision, and ghost routes; effects must not open the locked exit/basement
   or move a pickup. Approach/illuminate a silhouette and confirm it disappears.
4. Complete the unchanged fuse → clues → combination → crowbar → key → exit
   sequence. Open/reread inventory and notes during exploration. Check that
   environmental events stop for interfaces/near puzzles while ghost risk remains.
5. Evade a chase, hide, and leave hiding. Check the ensuing quiet periods.
   Let the real ghost catch you in open space and through a witnessed wardrobe
   inspection. Confirm a visible short encounter followed by CAUGHT; R must
   cleanly restart. Also try R during the encounter.
6. Repeat wins/catches/restarts, resize, and Alt-Tab during effects and encounters.
   Check restored colors, FOV, pointer capture, and fresh input. Try accessibility
   constants in a new run and restore your preferred values afterward.

Remaining limits: faint geometric placeholders, no sound/cinematics/story assets,
approximate local lighting, decorative cabinet motion rather than autonomous
passage doors, composited camera-space catch presentation, and no save system.
Long-session memory profiling, physical mouse/Alt-Tab, motion-comfort assessment,
and suspense/resource balance with a human player remain unverified. Existing
Panda3D icon/profile/framebuffer/foreground warnings remain nonfatal.

Modified files: `game/systems/horror_manager.py`, `game/ghost/jumpscare.py`,
`game/game_manager.py`, `game/scene_manager.py`, `game/settings.py`,
`game/ui/inventory_ui.py`, `game/tests/test_prototype.py`,
`game/tests/windowed_smoke.py`, and this `README.md`. No new code modules or
folders were needed; no commit, push, or merge was performed.

For Milestone 6, prioritize human pacing/motion-comfort tests and resource balance,
then clearer procedural scare silhouettes/prop affordances and accessibility
controls. Design checkpoint semantics for inventory/puzzles/events before adding
persistence. Add an authored sound/story pass only when that asset work is approved.

## Milestone 4: inventory, puzzles, and story progression

This milestone adds a complete authored puzzle sequence to the existing house.
The earlier milestone sections below record their historical behavior and tests;
the current controls and progression in this section take precedence.

Inventory, notes, and combination screens **keep gameplay active**. Ghost
perception, pursuit, inspections, flashlight drain/flicker, stamina recovery, and
hidden breathing continue. Movement, mouse look, E, and F are blocked while a
screen is open. Close it before moving, leaving hiding, or toggling the torch.
The pointer remains captured because these interfaces use keyboard controls.
Opening/closing clears held keys and mouse velocity, requiring a fresh movement
press. Escape closes a screen without also quitting or interacting with the world.
Actual focus loss still pauses the game and releases capture; refocusing preserves
the open screen. Death, escape, and R restart close screens and clean their state.

Select an item with Up/Down. Names, descriptions, quantities, and inspection are
available; Enter rereads stored notes. Select a battery and press U, then Enter
to use one. Backspace cancels. Full charge or a missing flashlight keeps the
battery. Enter alone does not use a battery, and repeated Enter cannot consume
another after a completed confirmation. Keys, notes, and tools are unique;
reusable tools cannot be consumed. Essential items cannot be dropped or discarded.

| Item/interaction | Location | Approach `(x, z)` | Result |
| --- | --- | --- | --- |
| Flashlight | Foyer console | `(0, -16)` | F toggles the existing beam |
| Keeper's Instructions | Living-room table | `(-6.8, -9)` | Stored note explains the order and fuse location |
| Ceramic Fuse | Storage boxes beside east wall | `(-12.8, -2)` | Unique installation item |
| Electrical box | Kitchen cabinet front | `(-11.4, 8.1)` | E installs fuse once and powers the dining lockbox |
| Battery | Kitchen counter | `(-15, 5)` | Stored; restores up to 35% charge when confirmed |
| Household Tally | Kitchen counter drawer | `(-15.3, 10.3)` | Available after power; counts complete the clue |
| Four-wheel lockbox | Dining-room cabinet | `(-3.2, 8.5)` | Correct code awards the reusable crowbar once |
| Boarded cabinet | Bedroom Two bedside console | `(7.2, 9)` | E with crowbar removes boards; tool kept |
| Exit Key | Inside opened bedside cabinet | `(7.2, 9)` | Collect separately after removing boards |
| Final exit | North exit area | `(0, 16.3)` | E unlocks; wait for opening, then walk through |

Power changes the electrical box's indicator and unlock availability, without
changing house ambient/fill lighting, flashlight brightness/shadows, or fog.
Puzzle panels sit against furniture; they add no hallway barriers. All 15 areas,
43 navigation nodes, 53 edges, and escape loops remain. Basement stays sealed.
Wrong combinations have no attempt limit, cost, or permanent lockout. Installation,
safe rewards, and board removal persist only for the current playthrough and reset
on R. The key pickup is disabled until board removal; the tally is disabled until
power. Reward items cannot be permanently lost through the interface.

The objective HUD follows actual state: collect flashlight → find fuse → install
fuse → read clues/open dining lockbox → pry bedroom cabinet → collect key → exit.
It never displays the combination. Collected notes can be reread at any time.

<details>
<summary>Developer solution / manual-test spoiler</summary>

The first note specifies portraits, bells, cradles, chairs. The tally gives two,
four, one, seven respectively, so the authored combination is **2417**. This value
lives in structured level data; the game HUD and lock screen do not reveal it.

</details>

### Validation and limits

- Baseline: all 69 pre-milestone tests passed before editing.
- Expanded suite: **88 tests passed in 67.804 seconds**: the 69 named cases are
  retained, plus 19 regressions for quantities, unique items, guarded battery use,
  modal controls/focus/resize, fuse/power, code attempts, crowbar, note rereading,
  objectives/restarts, active ghost capture, hiding risk, dependencies, and escape.
- The legacy battery cases now assert stored pickup followed by deliberate use;
  legacy key/rendering checks explicitly set up completed puzzle gates. A new
  end-to-end case walks the real controller through the entire gated sequence.
- Level validation rejects unknown gates, missing rewards, cyclic dependencies,
  invalid combinations, and room-external approaches. Existing collision, wall,
  navigation, movement/FPS, lighting, survival, and restart tests remain active.
- The native `main.py` smoke script uses actual engine key dispatch, W movement,
  collision rays, notes/inventory, incorrect/correct code, crowbar, key, escape,
  and R. The ghost is disabled only for deterministic puzzle routing and frozen
  for lighting images; the same run separately exercises live inspection/capture.
- All interface screenshots were visually reviewed, including 640×480 inventory.
  Nine same-position flashlight OFF/ON comparisons passed; no new shader exceptions
  or white-surface artifacts appeared. Settings AST matches the committed baseline.
- This is scripted engine testing, **not human playtesting**. Native Windows was
  available, so no Linux virtual display was needed. Programmatic focus loss was
  refused by Windows; direct focus handling passed, while real Alt-Tab is unverified.
- Startup timing on the RTX 3050 Laptop GPU was approximately 7 ms median; this
  is a local scripted observation, not a minimum-spec or student-laptop benchmark.
- Limits: keyboard-only interfaces, instant placeholder compartment interactions,
  automatic crowbar reward, no saving, no full cinematics/audio, and only the existing
  single battery pickup. Resource balance and reading/puzzle safety against a live
  ghost need human playtesting. Existing perception and flashlight shadow limits
  remain documented in the earlier milestone sections.

Run validation from this project directory:

```powershell
.\.venv\Scripts\python.exe -m compileall -q main.py game
.\.venv\Scripts\python.exe -m unittest discover -s game/tests -v
git diff --check
.\.venv\Scripts\python.exe -m game.tests.windowed_smoke
```

Screenshots are generated test evidence, ignored by Git, and are not game assets:
[inventory](game/tests/render_progression_inventory.png),
[640×480 inventory](game/tests/render_progression_inventory_640x480.png),
[battery confirmation](game/tests/render_progression_battery_confirmation.png),
[keeper note](game/tests/render_progression_note.png),
[tally](game/tests/render_progression_tally.png),
[fuse box](game/tests/render_progression_fuse_box.png),
[combination](game/tests/render_progression_combination.png),
[objective](game/tests/render_progression_objective.png),
[escape](game/tests/render_progression_escape.png).

### Manual playtest

1. Run `.\.venv\Scripts\python.exe main.py`. Collect the flashlight with E;
   verify F and normal WASD/mouse/Shift/Ctrl controls.
2. Read the living-room note with E. Try WASD, E, F, and mouse look while reading:
   player controls should be blocked while the ghost and battery remain active.
   Escape closes the note. Tab → select note → Enter should reread it.
3. Try the fuse box, dining lockbox, boarded cabinet, and exit before obtaining
   their requirements. Each should refuse safely with feedback.
4. Follow the location table: collect storage fuse, install at kitchen box,
   read released tally, infer code, open dining lockbox, take automatic crowbar,
   pry bedroom boards, and collect the key. Try a wrong code and close/reopen the
   lock before submitting the solution; retries must remain possible.
5. Collect the blue kitchen battery. Select it in Tab inventory; U/Backspace
   must cancel, U/Enter must use one, and a full flashlight must keep the item.
6. Use hiding and alternate house routes while the ghost is active. Open each
   screen during pursuit: it must not pause or grant immunity. Close quickly to
   escape; reading while hidden must not disable breathing/inspection risk.
7. Unlock the north exit with E, wait for the 0.8-second opening, then cross.
   R after escape and after capture must clear inventory, puzzles, objectives,
   hiding, and ghost memory without exceptions.
8. Resize the window, Alt-Tab with each screen open, return, close the screen,
   and press movement anew. Check pointer capture, legible text, and no stuck keys.

### Files changed

| Group | Files |
| --- | --- |
| New modules (existing directories) | `game/systems/progression.py`, `game/world/puzzles.py` |
| Inventory/pickups | `game/items/inventory.py`, `game/items/item.py`, `game/items/battery.py`, `game/items/key.py` |
| UI and controls | `game/ui/inventory_ui.py`, `game/ui/hud.py`, `game/game_manager.py`, `game/player/player.py`, `game/player/interaction.py` |
| Level and construction | `game/scene_manager.py`, `game/world/house.py`, `game/levels/haunted_house.py`, `game/levels/haunted_house.json`, `game/data/items.json`, `game/data/spawn_points.json` |
| Validation | `game/tests/test_inventory.py`, `game/tests/test_level_data.py`, `game/tests/test_prototype.py`, `game/tests/windowed_smoke.py` |
| Documentation | `README.md` |

No ghost AI/navigation, lighting settings, external assets, or house room geometry
were replaced. No automatic commit, push, or merge was performed.

### Suggested Milestone 5

Start with human playtests to tune battery supply, clue readability, ghost pressure,
and safe reading locations. Improve geometric affordances for opened compartments,
then add accessibility options and remappable controls. After this sequence feels
reliable, plan authored story beats and a small audio pass; design save/checkpoint
semantics around puzzle and inventory state before implementing persistence.

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

## Milestone 3: perception, searching and survival

Development started from clean `main` commit `af6b65a`, with all 46 existing
tests passing. All original test cases remain; sensor fixtures now emit discrete
sound events and wait for detection buildup. State/recovery tests use the new
search duration and bounded AI timestep. The suite adds 23 survival regressions
for **69 tests**. The haunted-house footprint, room connections, waypoint graph,
pickups and exit objectives remain intact. Milestone 2.5's ambient light, flashlight
brightness, attenuation, shadows and fog settings are unchanged.

Vision still requires horizontal FOV, distance and real collider LOS; walls and
closed doors block it. Darkness and crouching reduce the detection distance and
buildup rate. The lit flashlight raises visibility, including its actual dark
flicker intervals. Detection accumulates while the target is visible and decays
when occluded. A ghost examines a silhouette before acquiring it, rather than
instantly chasing. Confirmed CHASE retains the existing close-range LOS catch.

Footsteps are immutable position/strength/time events emitted at actual movement
substeps. Sprinting emits louder pulses than walking; crouching emits quieter,
less frequent pulses. Pushing a wall emits nothing and spends no stamina.
Unheard/old events expire after 1.5 seconds; a bounded queue prevents buildup.
Hearing uses each recorded source rather than the player's current position,
attenuates through obstructing colliders, and accepts new investigation sources
at most once per 0.8 seconds. Focus loss and restart clear pending noises.
These are gameplay noise events; no audio assets or audio playback was added.

The existing five states now behave as follows:

| State | Behavior |
| --- | --- |
| PATROL | Uses existing meaningful room destinations and collision-aware A* |
| INVESTIGATE | Travels to an accepted sound snapshot or a witnessed wardrobe entrance |
| SEARCH | Visits reachable nearby waypoints and plausible wardrobes, with a bounded 14-second budget |
| CHASE | Pursues visible players at 5.9 units/s; after LOS breaks, follows the last seen location and then searches |
| JUMPSCARE | Catches through unobstructed close-range LOS, or after physically reaching and inspecting the occupied wardrobe |

Last-known position expires after 12 seconds without fresh evidence. Search
uncertainty starts at 0.3 units for sight / 1.8 for sound and grows at 0.6 units/s;
the candidate radius expands around that belief. Searches never query hidden
occupancy to choose destinations. An empty wardrobe does not reveal occupants
elsewhere. Existing edge validation, width sweeps, stuck replanning and four-second
no-route recovery remain. AI substeps at most 1/30 second preserve elapsed time
and reduce FPS-dependent transitions. The ghost never teleports.

Two existing bedroom cabinets now have `hiding: true` in level data and hollow
placeholder walls with a narrow viewing slit. Their footprints and solid outside
colliders are unchanged. Aim at a wardrobe and press E to enter; E exits without
requiring another ray hit. Hidden players cannot walk, crouch further or sprint;
mouse turning is limited to +/-25 degrees yaw and +/-20 pitch. Entry requires
a safe return position, and leaving validates candidate positions, floor support,
body clearance and exit sweeps. If every exit is obstructed, it waits and displays
feedback instead of clipping through the wall. Reentry has a one-second delay.

An unseen hidden player is not a normal vision/catch target. A ghost that sees
entry remembers that wardrobe and may inspect it. Suspicious searches can inspect
nearby wardrobes regardless of occupancy. Inspection takes 1.5 seconds after
reaching the entrance with a clear ray, with a HUD warning and an opportunity to
leave. Reentering an actively checked wardrobe cannot restart the inspection.
After 12 seconds hiding, breathing noise starts and repeats every three seconds;
passing patrols can hear it and investigate. No arbitrary global hiding timeout
or automatic through-wall capture was added.

Stamina is shown in the existing inventory HUD. Configuration is in
`game/settings.py`:

| Setting | Default |
| --- | --- |
| Walk / sprint / crouch speed | 5 / 8 / 2.2 units/s |
| Maximum stamina | 100 |
| Actual sprint drain | 22 points/s (about 4.55 seconds from full) |
| Recovery | 15 points/s after a one-second delay |
| Exhaustion release threshold | 25 points |
| Detection buildup base | 0.65 seconds, slower at distance/in darkness/when crouched |
| Ghost chase / search speed | 5.9 / 2.2 units/s |

Drain, recovery, noise and movement use elapsed substeps, including depletion
partway through a slow frame. A depleted player walks until enough stamina is
restored, avoiding rapid sprint/walk oscillation. Ctrl lowers the camera smoothly
and updates the actual body collider. Standing checks headroom over the whole
footprint; changing stance also checks destination headroom to prevent the two
controller rays from straddling a thin low ceiling. Floor normals are normalized
when validating hiding exits because Panda's transformed normals retain scale.

Validation covers LOS/closed doors, discrete hearing and cooldown, memory and
lost sight, connected searching, safe/blocked exits, unwitnessed/witnessed hiding,
empty wardrobe checks, escape during inspection, reentry abuse, breathing risk,
stamina, crouch headroom, and restart/focus cleanup. Movement, stamina, crouch
camera/noise and detection buildup are compared at simulated 4/30/60/120 FPS.
The original collision, navigation recovery, flashlight pixel/shadow, inventory
and escape tests remain included.

The native smoke harness launches the real main.py and dispatches Ctrl/W/Shift/E,
checks stamina drain/recovery, enters/exits a wardrobe, and runs live witnessed
inspection through capture and R restart. It poses fixtures, freezes AI during
movement setup, and uses fixed timesteps; this is scripted engine testing, not
a human playthrough. It also retains resizing, six original R restarts and all
nine OFF/ON lighting comparisons. Native survival screenshots are
`render_survival_{crouch,sprint,wardrobe,hidden,inspection,caught}.png` in the
existing ignored test screenshot location.

Final checks passed: all 69 tests in 51.7 seconds, compilation and
`git diff --check`. The final native live-AI startup sample measured 7.04 ms
median / 11.22 ms p95 per task-manager frame on the RTX 3050 Laptop GPU. This
short sample does not establish lower-end laptop performance or longer-session
stability. Existing PNG-profile, missing-icon and programmatic foreground
warnings remain; no new shader errors or gameplay exceptions were observed.

Known limits: visibility uses stance/flashlight/distance heuristics rather than
sampling illumination on the player; sound obstruction uses one ray and a
multiplier rather than acoustic propagation. The ghost cannot operate doors.
Wardrobe entry is immediate, without an animation. AI/stamina/hiding balance,
physical pointer input, actual Alt+Tab, prolonged sessions and lower-end hardware
still need human testing. No unresolved failure remains in the automated cases.

Milestone 3 modified files:

| Area | Files |
| --- | --- |
| Configuration | `game/settings.py`, `game/levels/haunted_house.json` |
| Player/survival | `game/player/player.py`, `game/player/player_stats.py`, `game/player/camera_controller.py`, `game/player/interaction.py` |
| AI/perception | `game/ghost/ghost_ai.py`, `game/ghost/ghost_vision.py`, `game/ghost/ghost_hearing.py`, `game/ghost/ghost.py` |
| Wardrobes/world | `game/world/room.py`, `game/world/house.py` |
| Lifecycle/HUD | `game/scene_manager.py`, `game/game_manager.py`, `game/ui/inventory_ui.py` |
| Verification | `game/tests/test_prototype.py`, `game/tests/windowed_smoke.py`, `README.md` |

Milestone 3 manual checks after launching normally:

1. Hold Ctrl while moving through a room; release it to stand. Confirm lower
   view, slower movement and intact wall/furniture collisions. The current house
   has no deliberate crouch-only passage; regression fixtures test low headroom.
2. Shift-sprint through clear corridors, observe stamina drain, then walk/rest
   to recover. At exhaustion, confirm walking until 25% charge. Pushing a wall
   should generate neither new footstep events nor sprint drain.
3. Break ghost LOS around a doorway and take another loop. It should investigate
   remembered evidence and search reachable rooms rather than track through walls.
4. In either bedroom, aim at the tall brown wardrobe and press E. Try WASD and
   turning the mouse; movement must stay locked and viewing limited. E should
   return to clear floor. Inspect the HUD after resizing while hidden/crouched.
5. Enter unseen, then compare entering while watched. A witnessed entry should
   prompt an inspection; leave during its warning and sprint away. Reentry must
   not reset an active inspection. Staying more than 12 seconds creates periodic
   breathing noise; a nearby patrol may investigate, rather than instant capture.
6. Repeat win/loss and R from crouching/hiding/exhaustion. Confirm fresh stamina,
   inventory, camera, AI memory and wardrobes. Alt+Tab while hidden to verify
   pause/capture restoration. Complete the existing key/battery/exit checks below.

Milestone 4 recommendations: first human-playtest evasion routes, discovery and
stamina economy, run longer restart/focus soaks, and profile a lower-end laptop.
Then add inspectable clues and a small authored puzzle with explicit item/exit
softlock tests. Improve SEARCH coverage and sound propagation from observed
playtest problems, and scope hiding animation/door handling separately. Saving,
new levels and imported/audio assets remain future work.

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
