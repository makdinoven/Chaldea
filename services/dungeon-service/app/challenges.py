"""
Class challenges (FEAT-176): what a party member does outside battle — a short
minigame, or a plain roll for those who would rather not play.

Pure rules only, no I/O, so the server's verdict and the browser's picture of
the game are the same computation (the frontend mirrors `lockpick_verdict`).

Secret ways out of a room, one per class: a hidden mechanism (rogue), an
illusory wall (mage), a cave-in (warrior). Where the mechanism lever is and
which stones hold the cave-in up stay on the server; the player learns them
one move at a time (`mechanism_probe`, `rubble_pull`).

The warrior's own: the party shield (blows to turn aside, raised before the
party moves on) and holding up a portcullis or a slab until it is propped.

The mage breaks a magic seal by tracing its sigil node by node; the rogue
searches a room for a stash by the traces that point to it. Both are played
move by move: the sigil's path and the stash's place stay on the server.

The lock (rogue's craft): pins in a row; the active one bobs up and down, and a
press while its tip is inside the shear window sets it and wakes the next.
A press outside the window strains the pick; too many and it breaks. The
character's agility widens the window and slows the pins; a member who is not
a rogue gets a narrower window, one more pin and fewer strains to spare.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

CLASS_WARRIOR = 1
CLASS_ROGUE = 2
CLASS_MAGE = 3

KIND_LOCKPICK = "lockpick"
KIND_MECHANISM = "mechanism"
KIND_ILLUSION = "illusion"
KIND_RUBBLE = "rubble"
KIND_SHIELD = "shield"
KIND_GATE = "gate"
KIND_SEAL = "seal"
KIND_SEARCH = "search"
# Standing watch at a rest: a plain roll, no game.
KIND_WATCH = "watch"
# Looking ahead (FEAT-176): the rogue scouts a corridor and disarms its trap; the mage reads a portal or an event.
KIND_SCOUT = "scout"
KIND_DISARM = "disarm"
KIND_INSIGHT = "insight"
SECRET_KINDS = (KIND_MECHANISM, KIND_ILLUSION, KIND_RUBBLE)
# Played move by move with the server (it keeps what must stay hidden).
STEP_KINDS = (KIND_MECHANISM, KIND_RUBBLE, KIND_SEAL, KIND_SEARCH, KIND_DISARM)
# Only ever a plain roll.
ROLL_ONLY_KINDS = (KIND_WATCH,)
# Whose craft each challenge is, and the stat it leans on.
KIND_CLASS: Dict[str, int] = {
    KIND_LOCKPICK: CLASS_ROGUE,
    KIND_MECHANISM: CLASS_ROGUE,
    KIND_ILLUSION: CLASS_MAGE,
    KIND_RUBBLE: CLASS_WARRIOR,
    KIND_SHIELD: CLASS_WARRIOR,
    KIND_GATE: CLASS_WARRIOR,
    KIND_SEAL: CLASS_MAGE,
    KIND_SEARCH: CLASS_ROGUE,
    KIND_WATCH: CLASS_WARRIOR,
    KIND_SCOUT: CLASS_ROGUE,
    KIND_DISARM: CLASS_ROGUE,
    KIND_INSIGHT: CLASS_MAGE,
}
KIND_STAT: Dict[str, str] = {
    KIND_LOCKPICK: "agility",
    KIND_MECHANISM: "agility",
    KIND_ILLUSION: "intelligence",
    KIND_RUBBLE: "strength",
    KIND_SHIELD: "strength",
    KIND_GATE: "strength",
    KIND_SEAL: "intelligence",
    KIND_SEARCH: "agility",
    KIND_WATCH: "strength",
    KIND_SCOUT: "agility",
    KIND_DISARM: "agility",
    KIND_INSIGHT: "intelligence",
}

# A plain roll: the stat, give or take ROLL_SPREAD, against the difficulty.
ROLL_SPREAD = 5
# Someone else's craft: a roll counts this much lower.
OFF_CLASS_PENALTY = 6

# --- the lock ---
PINS_MIN = 3
PINS_MAX = 6
# One more pin for every this many points of difficulty above the base.
PINS_DIFFICULTY_STEP = 5
PINS_BASE_DIFFICULTY = 8
# Half-width of the shear window, on the pin's travel from -1 to 1.
WINDOW_BASE = 0.24
WINDOW_PER_SKILL = 0.012
WINDOW_MIN = 0.1
WINDOW_MAX = 0.4
OFF_CLASS_WINDOW = 0.6
# How fast a pin bobs (cycles a second), a little quicker on harder locks.
FREQ_MIN = 0.4
FREQ_MAX = 1.2
FREQ_FLOOR = 0.28
# A deft hand sees the pin slower: each point of skill (stat over difficulty) slows it this much.
FREQ_SLOW_PER_SKILL = 0.02
FREQ_SKILL_FACTOR_MIN = 0.7
FREQ_SKILL_FACTOR_MAX = 1.3
FREQ_SPREAD = 0.3
FREQ_PER_DIFFICULTY = 0.02
STRAINS_ROGUE = 2
STRAINS_OTHERS = 1
TIME_BASE_MS = 6000
TIME_PER_PIN_MS = 2500
# A press counts if the pin was in the window then or this long before: the eye sees it, the hand follows.
PRESS_GRACE_MS = 70
# Presses closer together than this are no human's.
MIN_PRESS_GAP_MS = 80
# The browser's clock and ours disagree a little.
CLOCK_SLACK_MS = 1500


def roll(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> Tuple[bool, int]:
    """A plain roll: (passed, the total that was rolled)."""
    total = stat_value + rng.randint(-ROLL_SPREAD, ROLL_SPREAD) - (OFF_CLASS_PENALTY if off_class else 0)
    return total >= difficulty, total


def lockpick_params(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> dict:
    """The lock to pick: its pins (speed, phase, window) and the limits."""
    pins_count = PINS_MIN + max(0, (difficulty - PINS_BASE_DIFFICULTY) // PINS_DIFFICULTY_STEP)
    if off_class:
        pins_count += 1
    pins_count = max(PINS_MIN, min(PINS_MAX, pins_count))
    skill = stat_value - difficulty
    width = min(WINDOW_MAX, max(WINDOW_MIN, WINDOW_BASE + WINDOW_PER_SKILL * skill))
    if off_class:
        width = max(WINDOW_MIN, width * OFF_CLASS_WINDOW)
    slow = max(FREQ_SKILL_FACTOR_MIN, min(FREQ_SKILL_FACTOR_MAX, 1 - FREQ_SLOW_PER_SKILL * skill))
    pins = []
    for _ in range(pins_count):
        freq = FREQ_MIN + rng.random() * FREQ_SPREAD + FREQ_PER_DIFFICULTY * max(0, difficulty - 12)
        pins.append({
            "freq": round(max(FREQ_FLOOR, min(FREQ_MAX, freq * slow)), 3),
            "phase": round(rng.random() * 2 * math.pi, 3),
            "center": round(rng.uniform(-0.5, 0.5), 3),
            "width": round(width, 3),
        })
    return {
        "pins": pins,
        "strains": STRAINS_OTHERS if off_class else STRAINS_ROGUE,
        "time_limit_ms": TIME_BASE_MS + TIME_PER_PIN_MS * pins_count,
    }


def pin_height(pin: dict, since_ms: float) -> float:
    """Where a pin's tip is, from -1 to 1, `since_ms` after it woke."""
    return math.sin(2 * math.pi * pin["freq"] * since_ms / 1000 + pin["phase"])


def in_window(pin: dict, since_ms: float) -> bool:
    """The pin's tip is in the shear window now, or was a moment ago (PRESS_GRACE_MS)."""
    return any(abs(pin_height(pin, s) - pin["center"]) <= pin["width"]
               for s in (since_ms, since_ms - PRESS_GRACE_MS) if s >= 0)


def lockpick_verdict(params: dict, presses: List[int]) -> Tuple[bool, str]:
    """Replays the presses (ms from the start). Returns (opened, how it ended):
    "open", "broke" (too many strains), "time" (ran out) or "short" (stopped)."""
    pins = params["pins"]
    active = 0
    woke_at = 0
    strains = 0
    for t in presses:
        if t > params["time_limit_ms"]:
            return False, "time"
        pin = pins[active]
        if in_window(pin, t - woke_at):
            active += 1
            woke_at = t
            if active == len(pins):
                return True, "open"
        else:
            strains += 1
            if strains > params["strains"]:
                return False, "broke"
    return False, "short"


def presses_plausible(params: dict, presses: List[int], elapsed_ms: Optional[float]) -> bool:
    """Sorted, no faster than a hand, no more than the game allows, and not
    finished sooner than the time that has really passed."""
    if len(presses) > len(params["pins"]) + params["strains"] + 1:
        return False
    if any(t < 0 for t in presses):
        return False
    if any(b - a < MIN_PRESS_GAP_MS for a, b in zip(presses, presses[1:])):
        return False
    if presses != sorted(presses):
        return False
    if elapsed_ms is not None and presses and presses[-1] > elapsed_ms + CLOCK_SLACK_MS:
        return False
    return True


# ---------------------------------------------------------------- the illusory wall (mage)
# Runes on the wall light up one after another; the mage repeats the order.

RUNE_GLYPHS = 9
RUNES_MIN = 3
RUNES_MAX = 9
RUNE_FLASH_MIN_MS = 400
RUNE_FLASH_MAX_MS = 1000
RUNE_FLASH_BASE_MS = 700
RUNE_FLASH_PER_SKILL_MS = 10
RUNE_TIME_BASE_MS = 8000
RUNE_TIME_PER_RUNE_MS = 1500
# A mage of some skill reads one rune fewer.
RUNE_SKILL_SHORTCUT = 10


def runes_params(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> dict:
    skill = stat_value - difficulty
    length = RUNES_MIN + max(0, (difficulty - PINS_BASE_DIFFICULTY) // PINS_DIFFICULTY_STEP)
    if off_class:
        length += 2
    if skill >= RUNE_SKILL_SHORTCUT:
        length -= 1
    length = max(RUNES_MIN, min(RUNES_MAX, length))
    sequence: List[int] = []
    while len(sequence) < length:
        g = rng.randrange(RUNE_GLYPHS)
        if not sequence or sequence[-1] != g:
            sequence.append(g)
    flash = RUNE_FLASH_BASE_MS + RUNE_FLASH_PER_SKILL_MS * skill
    return {
        "glyphs": RUNE_GLYPHS,
        "sequence": sequence,
        "flash_ms": int(max(RUNE_FLASH_MIN_MS, min(RUNE_FLASH_MAX_MS, flash))),
        "mistakes": 0 if off_class else 1,
        "time_limit_ms": RUNE_TIME_BASE_MS + RUNE_TIME_PER_RUNE_MS * length,
    }


def runes_min_ms(params: dict) -> float:
    """The runes are shown one by one before anything can be touched: no answer comes sooner."""
    return len(params["sequence"]) * params["flash_ms"] - CLOCK_SLACK_MS


def runes_verdict(params: dict, inputs: List[int]) -> Tuple[bool, str]:
    """Replays the runes touched: (dispelled, "open" / "broke" / "short")."""
    sequence = params["sequence"]
    step = 0
    mistakes = 0
    for g in inputs:
        if g == sequence[step]:
            step += 1
            if step == len(sequence):
                return True, "open"
        else:
            mistakes += 1
            if mistakes > params["mistakes"]:
                return False, "broke"
    return False, "short"


def runes_plausible(params: dict, inputs: List[int]) -> bool:
    return (len(inputs) <= len(params["sequence"]) + params["mistakes"] + 1
            and all(isinstance(g, int) and 0 <= g < params["glyphs"] for g in inputs))


# ---------------------------------------------------------------- the hidden mechanism (rogue)
# A wall of stones; one hides the lever. Each stone pressed tells how many steps
# away the lever is. The rogue has a few presses to find it.

MECH_COLS = 5
MECH_ROWS = 4
MECH_PROBES_BASE = 5
MECH_PROBES_MIN = 2
MECH_PROBES_MAX = 8
MECH_SKILL_PER_PROBE = 4
MECH_OFF_CLASS_PROBES = 2


def mechanism_params(stat_value: int, difficulty: int, off_class: bool,
                     rng: random.Random = random) -> Tuple[dict, dict]:
    """(what the player sees, what stays on the server)."""
    probes = MECH_PROBES_BASE + (stat_value - difficulty) // MECH_SKILL_PER_PROBE
    if off_class:
        probes -= MECH_OFF_CLASS_PROBES
    probes = max(MECH_PROBES_MIN, min(MECH_PROBES_MAX, probes))
    public = {"cols": MECH_COLS, "rows": MECH_ROWS, "probes": probes}
    hidden = {"target": [rng.randrange(MECH_COLS), rng.randrange(MECH_ROWS)], "pressed": []}
    return public, hidden


def mechanism_probe(public: dict, hidden: dict, x: int, y: int) -> Tuple[int, Optional[str]]:
    """Press a stone: (steps to the lever, how it ended or None)."""
    if not (0 <= x < public["cols"] and 0 <= y < public["rows"]):
        raise ValueError("Такого камня нет")
    tx, ty = hidden["target"]
    distance = abs(x - tx) + abs(y - ty)
    hidden["pressed"].append([x, y])
    if distance == 0:
        return distance, "open"
    if len(hidden["pressed"]) >= public["probes"]:
        return distance, "broke"
    return distance, None


# ---------------------------------------------------------------- the cave-in (warrior)
# Stones of the cave-in, some of them holding the rest up. Cracks hint which —
# mostly truly. The warrior pulls stones until the way is clear; pulling a
# bearing stone brings the pile down (a brace holds once). The pile is laid
# bottom up (four, three, two): the lower a stone, the likelier it bears.

RUBBLE_STONES = 9
RUBBLE_TO_CLEAR = 4
RUBBLE_BEARING_BASE = 3
RUBBLE_BEARING_STEP = 6
RUBBLE_BEARING_BASE_DIFFICULTY = 10
RUBBLE_HONEST_BASE = 0.8
RUBBLE_HONEST_PER_SKILL = 0.01
RUBBLE_HONEST_MIN = 0.55
RUBBLE_HONEST_MAX = 0.95
RUBBLE_OFF_CLASS_HONESTY = 0.2
RUBBLE_SKILL_EXTRA_BRACE = 10
# The pile's rows from the bottom, and how much likelier a stone in each is to bear.
RUBBLE_ROWS = ((0, 1, 2, 3), (4, 5, 6), (7, 8))
RUBBLE_ROW_WEIGHTS = (3, 2, 1)


def _bearing_stones(count: int, rng: random.Random) -> List[int]:
    """Which stones hold the pile up: drawn one by one, the lower rows weighing more."""
    weight = {i: RUBBLE_ROW_WEIGHTS[r] for r, row in enumerate(RUBBLE_ROWS) for i in row}
    left = list(range(RUBBLE_STONES))
    chosen: List[int] = []
    for _ in range(count):
        pick = rng.uniform(0, sum(weight[i] for i in left))
        for i in left:
            pick -= weight[i]
            if pick <= 0:
                break
        chosen.append(i)
        left.remove(i)
    return chosen


def rubble_params(stat_value: int, difficulty: int, off_class: bool,
                  rng: random.Random = random) -> Tuple[dict, dict]:
    skill = stat_value - difficulty
    bearing_count = RUBBLE_BEARING_BASE + max(0, (difficulty - RUBBLE_BEARING_BASE_DIFFICULTY) // RUBBLE_BEARING_STEP)
    if off_class:
        bearing_count += 1
    bearing_count = min(RUBBLE_STONES - RUBBLE_TO_CLEAR, bearing_count)
    bearing = [False] * RUBBLE_STONES
    for i in _bearing_stones(bearing_count, rng):
        bearing[i] = True
    honesty = RUBBLE_HONEST_BASE + RUBBLE_HONEST_PER_SKILL * skill - (RUBBLE_OFF_CLASS_HONESTY if off_class else 0)
    honesty = max(RUBBLE_HONEST_MIN, min(RUBBLE_HONEST_MAX, honesty))
    cracks = []
    for b in bearing:
        heavy = b if rng.random() < honesty else not b
        cracks.append(rng.choice((2, 3)) if heavy else rng.choice((0, 1)))
    braces = (0 if off_class else 1) + (1 if skill >= RUBBLE_SKILL_EXTRA_BRACE else 0)
    public = {"cracks": cracks, "to_clear": RUBBLE_TO_CLEAR, "braces": braces}
    hidden = {"bearing": bearing, "pulled": [], "collapses": 0}
    return public, hidden


def rubble_pull(public: dict, hidden: dict, index: int) -> Tuple[bool, Optional[str]]:
    """Pull a stone: (it was safe, how it ended or None)."""
    if not 0 <= index < len(hidden["bearing"]) or index in hidden["pulled"]:
        raise ValueError("Этот камень не вынуть")
    hidden["pulled"].append(index)
    if hidden["bearing"][index]:
        hidden["collapses"] += 1
        if hidden["collapses"] > public["braces"]:
            return False, "broke"
        return False, None
    cleared = sum(1 for i in hidden["pulled"] if not hidden["bearing"][i])
    return True, ("open" if cleared >= public["to_clear"] else None)


# ---------------------------------------------------------------- the party shield (warrior)
# Blows come from the left, from above, from the right; each is foreshadowed a
# moment before it lands, and the shield must face it when it does. The share
# of blows turned aside is how firmly the shield is held (the block).

SHIELD_SIDES = 3
# A turn of the shield is sent as ms * SHIELD_CODE + side.
SHIELD_CODE = 4
SHIELD_START_SIDE = 1
SHIELD_BLOWS_BASE = 6
SHIELD_BLOWS_MAX = 10
SHIELD_BLOWS_STEP = 6
SHIELD_BLOWS_BASE_DIFFICULTY = 12
SHIELD_OFF_CLASS_BLOWS = 2
SHIELD_FIRST_MS = 1500
SHIELD_GAP_MIN_MS = 900
SHIELD_GAP_SPREAD_MS = 600
# A blow never comes before the one before it has landed and the next is shown.
SHIELD_GAP_OVER_WARN_MS = 200
SHIELD_WARN_BASE_MS = 800
SHIELD_WARN_PER_SKILL_MS = 15
SHIELD_WARN_MIN_MS = 350
SHIELD_WARN_MAX_MS = 1200
SHIELD_OFF_CLASS_WARN = 0.65
SHIELD_MIN_GAP_MS = 60
SHIELD_TAIL_MS = 800


def shield_params(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> dict:
    skill = stat_value - difficulty
    count = SHIELD_BLOWS_BASE + max(0, (difficulty - SHIELD_BLOWS_BASE_DIFFICULTY) // SHIELD_BLOWS_STEP)
    if off_class:
        count += SHIELD_OFF_CLASS_BLOWS
    count = min(SHIELD_BLOWS_MAX, count)
    warn = SHIELD_WARN_BASE_MS + SHIELD_WARN_PER_SKILL_MS * skill
    if off_class:
        warn *= SHIELD_OFF_CLASS_WARN
    warn = int(max(SHIELD_WARN_MIN_MS, min(SHIELD_WARN_MAX_MS, warn)))
    blows = []
    at = SHIELD_FIRST_MS
    for _ in range(count):
        blows.append({"at_ms": at, "side": rng.randrange(SHIELD_SIDES)})
        at += max(warn + SHIELD_GAP_OVER_WARN_MS, SHIELD_GAP_MIN_MS + rng.randrange(SHIELD_GAP_SPREAD_MS))
    return {
        "blows": blows,
        "warn_ms": warn,
        "start_side": SHIELD_START_SIDE,
        "time_limit_ms": blows[-1]["at_ms"] + SHIELD_TAIL_MS,
    }


def shield_verdict(params: dict, presses: List[int], until_ms: float) -> Tuple[int, int]:
    """Replays the turns of the shield: (blows turned aside, blows in all).
    Blows that would land after `until_ms` were never met."""
    turns = [(p // SHIELD_CODE, p % SHIELD_CODE) for p in presses]
    parried = 0
    for blow in params["blows"]:
        if blow["at_ms"] > until_ms:
            break
        side = params["start_side"]
        for t, s in turns:
            if t > blow["at_ms"]:
                break
            side = s
        if side == blow["side"]:
            parried += 1
    return parried, len(params["blows"])


def shield_plausible(params: dict, presses: List[int]) -> bool:
    if len(presses) > (len(params["blows"]) + 1) * SHIELD_CODE:
        return False
    if any(not isinstance(p, int) or p < 0 or p % SHIELD_CODE >= SHIELD_SIDES for p in presses):
        return False
    times = [p // SHIELD_CODE for p in presses]
    return all(b - a >= SHIELD_MIN_GAP_MS for a, b in zip(times, times[1:]))


# ---------------------------------------------------------------- the gate (warrior)
# A portcullis or a slab to hold up until it is propped. It drags down, now and
# then harder; holding pushes it up, letting go lets it sink. It has to be kept
# inside the band long enough; if it drops to the floor it slams shut.
# Played in fixed ticks, so the browser and the server replay it alike.

GATE_TICK_MS = 50
GATE_START = 0.45
GATE_SLAM = 0.05
GATE_GRAVITY = 0.9
GATE_PUSH = 2.0
GATE_DAMPING = 0.9
GATE_ZONE_CENTER = 0.68
GATE_ZONE_BASE = 0.22
GATE_ZONE_PER_SKILL = 0.008
GATE_ZONE_MIN = 0.16
GATE_ZONE_MAX = 0.34
GATE_OFF_CLASS_ZONE = 0.75
GATE_HOLD_BASE_MS = 3500
GATE_HOLD_PER_DIFFICULTY_MS = 250
GATE_HOLD_BASE_DIFFICULTY = 12
GATE_OFF_CLASS_HOLD_MS = 1000
GATE_SURGES_BASE = 2
GATE_SURGES_STEP = 8
GATE_SURGE_FIRST_MS = 1000
GATE_SURGE_FORCE_MIN = 1.2
GATE_SURGE_FORCE_SPREAD = 0.6
GATE_SURGE_DUR_MIN_MS = 400
GATE_SURGE_DUR_SPREAD_MS = 400
GATE_EXTRA_TIME_MS = 4000
GATE_MIN_TOGGLE_GAP_MS = 30
GATE_MAX_TOGGLES = 600


def gate_params(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> dict:
    skill = stat_value - difficulty
    width = max(GATE_ZONE_MIN, min(GATE_ZONE_MAX, GATE_ZONE_BASE + GATE_ZONE_PER_SKILL * skill))
    if off_class:
        width = max(GATE_ZONE_MIN, width * GATE_OFF_CLASS_ZONE)
    hold = GATE_HOLD_BASE_MS + GATE_HOLD_PER_DIFFICULTY_MS * max(0, difficulty - GATE_HOLD_BASE_DIFFICULTY)
    if off_class:
        hold += GATE_OFF_CLASS_HOLD_MS
    limit = hold * 2 + GATE_EXTRA_TIME_MS
    count = GATE_SURGES_BASE + difficulty // GATE_SURGES_STEP + (1 if off_class else 0)
    surges = []
    for _ in range(count):
        surges.append({
            "at_ms": GATE_SURGE_FIRST_MS + rng.randrange(max(1, limit - 2 * GATE_SURGE_FIRST_MS)),
            "dur_ms": GATE_SURGE_DUR_MIN_MS + rng.randrange(GATE_SURGE_DUR_SPREAD_MS),
            "force": round(GATE_SURGE_FORCE_MIN + rng.random() * GATE_SURGE_FORCE_SPREAD, 2),
        })
    surges.sort(key=lambda x: x["at_ms"])
    return {
        "zone": [round(GATE_ZONE_CENTER - width / 2, 3), round(GATE_ZONE_CENTER + width / 2, 3)],
        "hold_ms": hold,
        "surges": surges,
        "time_limit_ms": limit,
    }


def gate_step(params: dict, level: float, speed: float, holding: bool, t: int) -> Tuple[float, float]:
    """One tick of the gate: its new height (0 down … 1 up) and speed."""
    surge = sum(x["force"] for x in params["surges"] if x["at_ms"] <= t < x["at_ms"] + x["dur_ms"])
    accel = (GATE_PUSH if holding else 0.0) - GATE_GRAVITY - surge
    dt = GATE_TICK_MS / 1000
    speed = (speed + accel * dt) * GATE_DAMPING
    level += speed * dt
    if level >= 1.0:
        level, speed = 1.0, 0.0
    return level, speed


def gate_verdict(params: dict, toggles: List[int], until_ms: float) -> Tuple[bool, str]:
    """Replays the grip (ms of each press and release, in turn) tick by tick up
    to `until_ms`: (propped, "open" / "broke" (slammed) / "time" / "short")."""
    lo, hi = params["zone"]
    level, speed, held = GATE_START, 0.0, 0
    holding = False
    nxt = 0
    t = 0
    while t < params["time_limit_ms"]:
        if t > until_ms:
            return False, "short"
        while nxt < len(toggles) and toggles[nxt] <= t:
            holding = not holding
            nxt += 1
        level, speed = gate_step(params, level, speed, holding, t)
        if lo <= level <= hi:
            held += GATE_TICK_MS
            if held >= params["hold_ms"]:
                return True, "open"
        if level <= GATE_SLAM:
            return False, "broke"
        t += GATE_TICK_MS
    return False, "time"


def gate_plausible(toggles: List[int]) -> bool:
    if len(toggles) > GATE_MAX_TOGGLES or any(not isinstance(t, int) or t < 0 for t in toggles):
        return False
    return all(b - a >= GATE_MIN_TOGGLE_GAP_MS for a, b in zip(toggles, toggles[1:]))


# ---------------------------------------------------------------- the magic seal (mage)
# Nodes on a ring; the sigil runs from the lit one through a few others, never
# to a neighbour on the ring (a star). At each step the true next node
# resonates among a few false ones; a wrong touch sparks and rules it out.
# The circle beats steadily; the true node pulses in time with it, the false
# ones a little off the beat — the sharper the mind, the further off they are.

SEAL_NODES = 8
SEAL_STEPS_BASE = 4
SEAL_STEPS_MAX = SEAL_NODES - 1
SEAL_STEPS_STEP = 5
SEAL_STEPS_BASE_DIFFICULTY = 8
SEAL_DECOYS_MAGE = 1
SEAL_DECOYS_OTHERS = 2
SEAL_DECOYS_MAX = 3
SEAL_MISTAKES_MAGE = 1
SEAL_SKILL_EXTRA_MISTAKE = 10
SEAL_PATH_TRIES = 200
# The circle's beat, and how far off it the false nodes pulse (a share of the beat, 0..0.5).
SEAL_BEAT_MS = 1400
SEAL_OFFSET_BASE = 0.22
SEAL_OFFSET_PER_SKILL = 0.008
SEAL_OFFSET_MIN = 0.07
SEAL_OFFSET_MAX = 0.38
SEAL_OFF_CLASS_OFFSET = 0.55
# Each false node is off by the offset give or take this share of it.
SEAL_OFFSET_SPREAD = 0.2


def _ring_neighbours(a: int, b: int) -> bool:
    return (a - b) % SEAL_NODES in (1, SEAL_NODES - 1)


def _seal_path(steps: int, rng: random.Random) -> List[int]:
    """A star sigil: distinct nodes, no two in a row side by side on the ring."""
    for _ in range(SEAL_PATH_TRIES):
        path = [rng.randrange(SEAL_NODES)]
        while len(path) <= steps:
            options = [n for n in range(SEAL_NODES) if n not in path and not _ring_neighbours(n, path[-1])]
            if not options:
                break
            path.append(rng.choice(options))
        if len(path) == steps + 1:
            return path
    # Never needed in practice: fall back to any distinct nodes.
    return rng.sample(range(SEAL_NODES), steps + 1)


def _seal_pulsing(hidden: dict, rng: random.Random) -> List[int]:
    """The nodes resonating now: the true next one among a few false ones.
    Their pulses' offsets from the beat go to `hidden["offsets"]` (the true one 0)."""
    path, at = hidden["path"], hidden["at"]
    correct = path[at + 1]
    free = [n for n in range(SEAL_NODES)
            if n not in path[:at + 1] and n != correct and n not in hidden["ruled_out"]]
    decoys = rng.sample(free, min(len(free), hidden["decoys"]))
    pulsing = sorted([correct] + decoys)
    hidden["pulsing"] = pulsing
    off = hidden["offset"]
    hidden["offsets"] = [
        0.0 if n == correct
        else round(rng.choice((-1, 1)) * off * (1 + rng.uniform(-SEAL_OFFSET_SPREAD, SEAL_OFFSET_SPREAD)), 3)
        for n in pulsing
    ]
    return pulsing


def seal_params(stat_value: int, difficulty: int, off_class: bool,
                rng: random.Random = random) -> Tuple[dict, dict]:
    """(what the player sees, what stays on the server)."""
    skill = stat_value - difficulty
    steps = SEAL_STEPS_BASE + max(0, (difficulty - SEAL_STEPS_BASE_DIFFICULTY) // SEAL_STEPS_STEP)
    if off_class:
        steps += 1
    steps = min(SEAL_STEPS_MAX, steps)
    decoys = SEAL_DECOYS_OTHERS if off_class else SEAL_DECOYS_MAGE
    if skill < 0:
        decoys += 1
    decoys = min(SEAL_DECOYS_MAX, decoys)
    mistakes = 0 if off_class else SEAL_MISTAKES_MAGE + (1 if skill >= SEAL_SKILL_EXTRA_MISTAKE else 0)
    offset = max(SEAL_OFFSET_MIN, min(SEAL_OFFSET_MAX, SEAL_OFFSET_BASE + SEAL_OFFSET_PER_SKILL * skill))
    if off_class:
        offset = max(SEAL_OFFSET_MIN, offset * SEAL_OFF_CLASS_OFFSET)
    hidden = {"path": _seal_path(steps, rng), "at": 0, "mistakes": 0, "decoys": decoys,
              "ruled_out": [], "pulsing": [], "offset": round(offset, 3), "offsets": []}
    public = {"nodes": SEAL_NODES, "start": hidden["path"][0], "steps": steps, "mistakes": mistakes,
              "beat_ms": SEAL_BEAT_MS, "pulsing": _seal_pulsing(hidden, rng), "offsets": hidden["offsets"]}
    return public, hidden


def seal_trace(public: dict, hidden: dict, node: int,
               rng: random.Random = random) -> Tuple[bool, Optional[str], Optional[List[int]]]:
    """Touch a resonating node: (it was the true one, how it ended or None, the nodes resonating next)."""
    if node not in hidden["pulsing"]:
        raise ValueError("Этот узел не отзывается")
    if node == hidden["path"][hidden["at"] + 1]:
        hidden["at"] += 1
        hidden["ruled_out"] = []
        if hidden["at"] == public["steps"]:
            return True, "open", None
        return True, None, _seal_pulsing(hidden, rng)
    hidden["mistakes"] += 1
    hidden["ruled_out"].append(node)
    if hidden["mistakes"] > public["mistakes"]:
        return False, "broke", None
    return False, None, _seal_pulsing(hidden, rng)


# ---------------------------------------------------------------- searching a room (rogue)
# The room's floor in tiles; a stash may hide under one. Each tile looked at
# shows traces pointing one of eight ways — towards the stash, mostly; where
# there is no stash they lead nowhere. A rogue has more looks and truer traces.

SEARCH_COLS = 6
SEARCH_ROWS = 4
SEARCH_PROBES_ROGUE = 4
SEARCH_PROBES_OTHERS = 3
SEARCH_PROBES_MIN = 2
SEARCH_PROBES_MAX = 7
SEARCH_SKILL_PER_PROBE = 5
SEARCH_HONEST_BASE = 0.85
SEARCH_HONEST_PER_SKILL = 0.01
SEARCH_HONEST_MIN = 0.5
SEARCH_HONEST_MAX = 0.95
SEARCH_OFF_CLASS_HONESTY = 0.2
# Eight ways, clockwise from "up" (towards row 0).
SEARCH_WAYS = 8


def search_params(stat_value: int, difficulty: int, off_class: bool, has_stash: bool,
                  rng: random.Random = random) -> Tuple[dict, dict]:
    skill = stat_value - difficulty
    probes = (SEARCH_PROBES_OTHERS if off_class else SEARCH_PROBES_ROGUE) + skill // SEARCH_SKILL_PER_PROBE
    probes = max(SEARCH_PROBES_MIN, min(SEARCH_PROBES_MAX, probes))
    honesty = SEARCH_HONEST_BASE + SEARCH_HONEST_PER_SKILL * skill - (SEARCH_OFF_CLASS_HONESTY if off_class else 0)
    honesty = max(SEARCH_HONEST_MIN, min(SEARCH_HONEST_MAX, honesty))
    target = [rng.randrange(SEARCH_COLS), rng.randrange(SEARCH_ROWS)] if has_stash else None
    public = {"cols": SEARCH_COLS, "rows": SEARCH_ROWS, "probes": probes}
    hidden = {"target": target, "probed": [], "honesty": honesty}
    return public, hidden


def way_towards(x: int, y: int, tx: int, ty: int) -> int:
    """Which of the eight ways leads from (x, y) towards (tx, ty)."""
    return round(math.atan2(tx - x, -(ty - y)) / (2 * math.pi / SEARCH_WAYS)) % SEARCH_WAYS


def search_probe(public: dict, hidden: dict, x: int, y: int,
                 rng: random.Random = random) -> Tuple[Optional[int], Optional[str]]:
    """Look under a tile: (the way its traces point — None where the stash is, how it ended or None)."""
    if not (0 <= x < public["cols"] and 0 <= y < public["rows"]) or [x, y] in hidden["probed"]:
        raise ValueError("Здесь уже смотрели")
    hidden["probed"].append([x, y])
    target = hidden["target"]
    if target and [x, y] == target:
        return None, "open"
    if target and rng.random() < hidden["honesty"]:
        way = way_towards(x, y, target[0], target[1])
    else:
        way = rng.randrange(SEARCH_WAYS)
    if len(hidden["probed"]) >= public["probes"]:
        return way, "broke"
    return way, None


# ---------------------------------------------------------------- scouting a corridor (rogue): "Тени"
# The corridor in cells; lanterns over some of them flare in turn. The rogue
# steps cell by cell; being in a cell while its lantern is lit — stepping into
# it or standing in it — gets the rogue seen. Played in fixed ticks, so the
# browser and the server replay it alike.

SHADOW_TICK_MS = 25
SHADOW_CELLS_BASE = 7
SHADOW_CELLS_MAX = 11
SHADOW_CELLS_STEP = 6
SHADOW_OFF_CLASS_CELLS = 2
SHADOW_GUARDED = 0.6
SHADOW_FREQ_MIN = 0.35
SHADOW_FREQ_SPREAD = 0.3
SHADOW_DUTY_BASE = 0.42
SHADOW_DUTY_PER_SKILL = 0.008
SHADOW_DUTY_MIN = 0.25
SHADOW_DUTY_MAX = 0.6
SHADOW_OFF_CLASS_DUTY = 0.1
SHADOW_TIME_PER_CELL_MS = 2200
SHADOW_TIME_BASE_MS = 4000
SHADOW_MIN_GAP_MS = 80


def shadow_params(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> dict:
    skill = stat_value - difficulty
    cells = SHADOW_CELLS_BASE + max(0, (difficulty - 12) // SHADOW_CELLS_STEP) + (SHADOW_OFF_CLASS_CELLS if off_class else 0)
    cells = min(SHADOW_CELLS_MAX, cells)
    duty = SHADOW_DUTY_BASE - SHADOW_DUTY_PER_SKILL * skill + (SHADOW_OFF_CLASS_DUTY if off_class else 0)
    duty = round(max(SHADOW_DUTY_MIN, min(SHADOW_DUTY_MAX, duty)), 3)
    lamps = []
    for i in range(cells):
        if rng.random() < SHADOW_GUARDED:
            lamps.append({"freq": round(SHADOW_FREQ_MIN + rng.random() * SHADOW_FREQ_SPREAD, 3),
                          "phase": round(rng.random(), 3), "duty": duty})
        else:
            lamps.append(None)
    # Never two lamps flaring in lockstep side by side with no gap: at least one cell in three is dark.
    for i in range(2, cells):
        if lamps[i] and lamps[i - 1] and lamps[i - 2]:
            lamps[i - 1] = None
    return {"cells": cells, "lamps": lamps, "time_limit_ms": SHADOW_TIME_BASE_MS + SHADOW_TIME_PER_CELL_MS * cells}


def shadow_lit(lamp: Optional[dict], t: float) -> bool:
    """A lamp is lit for the first `duty` of each of its cycles."""
    if not lamp:
        return False
    cycle = (t / 1000 * lamp["freq"] + lamp["phase"]) % 1
    return cycle < lamp["duty"]


def shadow_verdict(params: dict, steps: List[int], until_ms: float) -> Tuple[bool, str]:
    """Replays the steps (ms of each) tick by tick: (through unseen, "open" / "broke" (seen) / "time" / "short").
    Position 0 is the start (dark), `cells` + 1 the far end (dark)."""
    cells, lamps = params["cells"], params["lamps"]
    pos, nxt, t = 0, 0, 0
    while t < params["time_limit_ms"]:
        if t > until_ms:
            return False, "short"
        while nxt < len(steps) and steps[nxt] <= t:
            pos += 1
            nxt += 1
            if pos > cells:
                return True, "open"
        if 1 <= pos <= cells and shadow_lit(lamps[pos - 1], t):
            return False, "broke"
        t += SHADOW_TICK_MS
    return False, "time"


def shadow_plausible(params: dict, steps: List[int]) -> bool:
    if len(steps) > params["cells"] + 2 or any(not isinstance(t, int) or t < 0 for t in steps):
        return False
    return all(b - a >= SHADOW_MIN_GAP_MS for a, b in zip(steps, steps[1:]))


# ---------------------------------------------------------------- disarming a trap (rogue): "Тяги"
# A row of rods, some of them taut (cutting one springs the trap). A slack rod
# cut shows how many of its two neighbours are taut. Cut every slack rod to
# disarm the trap. Which rods are taut only the server knows.

WIRES_BASE = 7
WIRES_MAX = 10
WIRES_OFF_CLASS = 2
WIRES_TAUT_BASE = 2
WIRES_TAUT_STEP = 6
WIRES_HINTS_BASE = 1
WIRES_SKILL_EXTRA_HINT = 8
WIRES_MISTAKES_ROGUE = 1


def wires_params(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> Tuple[dict, dict]:
    skill = stat_value - difficulty
    n = min(WIRES_MAX, WIRES_BASE + (WIRES_OFF_CLASS if off_class else 0))
    taut_count = min(n - 3, WIRES_TAUT_BASE + max(0, (difficulty - 12) // WIRES_TAUT_STEP) + (1 if off_class else 0))
    taut = [False] * n
    for i in rng.sample(range(n), taut_count):
        taut[i] = True
    hidden = {"taut": taut, "cut": [], "mistakes": 0}
    safe = [i for i in range(n) if not taut[i]]
    hints = WIRES_HINTS_BASE + (1 if skill >= WIRES_SKILL_EXTRA_HINT else 0) - (1 if off_class else 0)
    shown = {i: _taut_near(taut, i) for i in rng.sample(safe, max(0, min(len(safe) - 1, hints)))}
    public = {"wires": n, "taut": taut_count, "mistakes": 0 if off_class else WIRES_MISTAKES_ROGUE,
              "shown": [[i, c] for i, c in sorted(shown.items())]}
    # The hints come already cut: the player can't cut them again, so they count towards the end.
    hidden["cut"] = sorted(shown)
    return public, hidden


def _taut_near(taut: List[bool], i: int) -> int:
    return sum(1 for j in (i - 1, i + 1) if 0 <= j < len(taut) and taut[j])


def wires_cut(public: dict, hidden: dict, index: int) -> Tuple[bool, Optional[int], Optional[str]]:
    """Cut a rod: (it was slack, its taut neighbours — None for a taut one, how it ended or None)."""
    taut = hidden["taut"]
    if not 0 <= index < len(taut) or index in hidden["cut"]:
        raise ValueError("Эту тягу уже не перерезать")
    hidden["cut"].append(index)
    if taut[index]:
        hidden["mistakes"] += 1
        return False, None, ("broke" if hidden["mistakes"] > public["mistakes"] else None)
    done = all(taut[i] or i in hidden["cut"] for i in range(len(taut)))
    return True, _taut_near(taut, index), ("open" if done else None)


# ---------------------------------------------------------------- reading a portal or an event (mage): "Созвездие"
# Rings of a star chart, geared together: turning a ring turns the next one
# too. Turn them until every ring stands at its mark and the constellation is
# whole.

STARS_STEPS = 8
STARS_RINGS_BASE = 3
STARS_RINGS_MIN = 2
STARS_RINGS_MAX = 4
STARS_SKILL_FEWER = 10
STARS_TIME_BASE_MS = 14000
STARS_TIME_PER_RING_MS = 6000
STARS_TIME_PER_SKILL_MS = 300
STARS_MIN_GAP_MS = 60
STARS_MAX_TURNS = 80


def stars_params(stat_value: int, difficulty: int, off_class: bool, rng: random.Random = random) -> dict:
    skill = stat_value - difficulty
    rings = STARS_RINGS_BASE + (1 if off_class else 0) - (1 if skill >= STARS_SKILL_FEWER else 0)
    rings = max(STARS_RINGS_MIN, min(STARS_RINGS_MAX, rings))
    offsets = [rng.randrange(1, STARS_STEPS) for _ in range(rings)]
    time_limit = STARS_TIME_BASE_MS + STARS_TIME_PER_RING_MS * rings + STARS_TIME_PER_SKILL_MS * max(-10, min(10, skill))
    if off_class:
        time_limit = int(time_limit * 0.8)
    return {"rings": rings, "steps": STARS_STEPS, "offsets": offsets, "time_limit_ms": time_limit,
            "seed": rng.randrange(1_000_000)}


def stars_turn(offsets: List[int], ring: int, steps: int = STARS_STEPS) -> List[int]:
    """Turn a ring one step: it and the next ring move together."""
    out = list(offsets)
    for r in (ring, ring + 1):
        if 0 <= r < len(out):
            out[r] = (out[r] + 1) % steps
    return out


def stars_verdict(params: dict, turns: List[int]) -> Tuple[bool, str]:
    """Replays the turns (ring indexes): (whole, "open" / "short")."""
    offsets = list(params["offsets"])
    for ring in turns:
        offsets = stars_turn(offsets, ring, params["steps"])
        if all(o == 0 for o in offsets):
            return True, "open"
    return False, "short"


def stars_plausible(params: dict, turns: List[int]) -> bool:
    return len(turns) <= STARS_MAX_TURNS and all(isinstance(r, int) and 0 <= r < params["rings"] for r in turns)
