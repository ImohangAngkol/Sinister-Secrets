# The Keeper's Secret — internal story outline

The player investigates the Vale disappearances and comes to recover records.
The front entrance closes; the existing north exit is the escape route. No new
door, level, supernatural movement ability, or essential puzzle is introduced.

14 October 1987: Mara, Daniel and seven-year-old Elsie arrive (photograph).
16 October: exit relay maintenance is recorded. 17 October: the Keeper hears
Mara's voice from two places (journal). 18 October: he removes the fuse, locks
the pry bar behind the count wheels, and boards the exit key into the bedside
cabinet. Mara writes to Ruth (letter). 19 October: he refuses pleas at the north
door. 20 October: the family is absent, but their pleas repeat (observation log).
23 October: a notice records their disappearance; no bodies were recovered.
2 November: the Keeper confesses responsibility for trapping them, leaving the
existing instructions and tally as a way to undo his locks. An undated folded
record questions whether the figure wearing his coat is a person or an echo.

Central discovery: the Keeper's fear of imitation led him to imprison the real
family. Their ultimate fate and the moving figure's identity remain uncertain.
The truth ending exposes this human decision; it does not claim forensic proof
of the ghost's identity. The escape ending leaves the mystery unresolved.

Eight optional records live in `game/data/story.json`; level loading merges them
into existing item/spawn data without overriding mechanical IDs. Five records,
including journal, observation log and confession, unlock a choice of Truth or
Escape. No optional record is puzzle-gated or required to escape. The discovered
journal shows the evidence rule, without spoiling undiscovered document titles.

Six authored encounters follow instructions, power, journal, lockbox, approaching
the bedroom cabinet, and approaching the exit with evidence. Captions convey
every story beat without sound. Once started, an encounter is recorded, even if
danger or an interface interrupts it, preventing repeated surprise/rewards.
Encounter timers and cinematic playback freeze on focus loss/pause. Temporary
visuals, transforms and audio are never serialized. Retry restores exactly the
checkpoint's evidence/events, so encounters occurring after that snapshot may
occur again; this is snapshot recovery, not a global completion ledger.

Introduction and endings use four seven-second cards, skippable with Enter or
Escape. No flashing, mandatory camera motion or real-ghost relocation is used.
Normal gameplay resumes in the authored foyer after introduction. Continue,
Retry and terminal R restart never replay it. New Game does replay it.
