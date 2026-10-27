"""Night Survivors game rules, one fixed time step at a time.

No pygame here: this file only knows about the game state as plain numbers,
so the tests can run it without a window. main.py draws this state.

Every number comes from data/game.json, so changing a number needs no code.
"""

import math
import random

TAU = math.pi * 2


# ---------------------------------------------------------------- the state

def new_weapon(kind, level):
    return {"kind": kind, "level": level, "cooldown": 0.0, "pulse": 0.0}


def new_game(spec, rng=None):
    hero = spec["hero"]
    return {
        "spec": spec,
        "rng": rng or random.Random(),
        "state": "playing",
        "time": 0.0,
        "kills": 0,
        "level": 1,
        "xp": 0,
        "cards": [],
        "hero": {
            "x": 0.0,
            "y": 0.0,
            "hp": hero["hp"],
            "max_hp": hero["hp"],
            "angle": 0.0,
        },
        "target": None,
        "weapons": {"spark_wand": new_weapon("spark_wand", 1)},
        "passives": {},
        "enemies": [],
        "sparks": [],
        "gems": [],
        "spawn_timer": 0.0,
        "boss_spawned": False,
        # the "feel" state: main.py draws these, they hold no game rules
        "floaters": [],   # damage numbers: {"x", "y", "life", "amount"}
        "flashes": [],    # white flash when an enemy dies: {"x", "y", "life", "radius"}
        "shake": 0.0,     # seconds of screen shake left
        "events": [],     # what just happened, for the sounds; main.py empties it
    }


def item_level(game, kind):
    """The level of a weapon or passive you have, or 0 when you do not have it."""
    entry = game["weapons"].get(kind) or game["passives"].get(kind)
    return entry["level"] if entry else 0


def hero_speed(game):
    """Walking speed with Swift Boots taken into account."""
    spec = game["spec"]
    boots = item_level(game, "swift_boots")
    return spec["hero"]["speed"] * (1 + boots * spec["passives"]["swift_boots"]["speed_bonus"])


def magnet_radius(game):
    spec = game["spec"]
    return spec["hero"]["magnet_radius"] + item_level(game, "magnet") * spec["passives"]["magnet"]["radius"]


def xp_needed(spec, level):
    """5 XP for level 2, then 8, 11, 14, ..."""
    return spec["xp"]["first_level"] + (level - 1) * spec["xp"]["per_level"]


def heal(game, amount):
    hero = game["hero"]
    hero["hp"] = min(hero["hp"] + amount, hero["max_hp"])


# ------------------------------------------------------------------- the feel

def _event(game, name):
    """Note that something happened, so main.py can play its sound."""
    game["events"].append(name)


def _add_number(game, x, y, amount):
    """One damage number that floats up and then disappears."""
    feel = game["spec"]["feel"]
    if len(game["floaters"]) < feel["max_numbers"]:
        game["floaters"].append({"x": x, "y": y,
                                 "life": feel["number_time"],
                                 "amount": amount})


def _hurt_enemy(game, enemy, amount):
    """Take damage off one enemy. The number and the hit sound follow."""
    enemy["hp"] -= amount
    _add_number(game, enemy["x"], enemy["y"], amount)
    _event(game, "hit")


def _add_flash(game, enemy):
    """The short white flash that says this enemy is gone."""
    feel = game["spec"]["feel"]
    if len(game["flashes"]) < feel["max_flashes"]:
        game["flashes"].append({"x": enemy["x"], "y": enemy["y"],
                                "life": feel["flash_time"],
                                "radius": game["spec"][enemy["kind"]]["radius"]})


def _start_shake(game):
    """The screen shakes a little when the hero is hurt."""
    game["shake"] = game["spec"]["feel"]["shake_time"]


def _update_feel(game, dt):
    """Age the damage numbers, the death flashes and the shake."""
    for item in game["floaters"]:
        item["life"] -= dt
    game["floaters"] = [f for f in game["floaters"] if f["life"] > 0]
    for item in game["flashes"]:
        item["life"] -= dt
    game["flashes"] = [f for f in game["flashes"] if f["life"] > 0]
    game["shake"] = max(0.0, game["shake"] - dt)


# ------------------------------------------------------------- weapon numbers

def wand_config(spec, level):
    base = spec["spark_wand"]
    extra = level - 1
    return {
        "damage": base["level_1"]["damage"] + extra * base["extra_level"]["damage"],
        "period": base["level_1"]["period"] - extra * base["extra_level"]["period"],
        "sparks": base["level_1"]["sparks"] + sum(
            1 for lv in base["extra_spark_levels"] if lv <= level),
    }


def blades_config(spec, level):
    base = spec["spin_blades"]
    extra = level - 1
    return {
        "damage": base["level_1"]["damage"] + extra * base["extra_level"]["damage"],
        "blades": base["level_1"]["blades"] + sum(
            1 for lv in base["extra_blade_levels"] if lv <= level),
    }


def ring_config(spec, level):
    base = spec["holy_ring"]
    extra = level - 1
    return {
        "damage": base["level_1"]["damage"] + extra * base["extra_level"]["damage"],
        "radius": base["level_1"]["radius"] + extra * base["extra_level"]["radius"],
    }


# ------------------------------------------------------------------- spawning

def min_alive(spec, time):
    """The minimum number of enemies that should be alive at this time."""
    wave = current_wave(spec, time)
    return wave["min_alive"] if wave else 0


def current_wave(spec, time):
    """The wave row that is in force at this time, or None before the first."""
    wave = None
    for row in spec["spawn"]["waves"]:
        if time >= row["from"]:
            wave = row
    return wave


def _spawn(game, kind, count):
    spawn = game["spec"]["spawn"]
    rng = game["rng"]
    enemy = game["spec"][kind]
    for _ in range(count):
        angle = rng.random() * TAU
        game["enemies"].append({
            "kind": kind,
            "x": game["hero"]["x"] + math.cos(angle) * spawn["circle_distance"],
            "y": game["hero"]["y"] + math.sin(angle) * spawn["circle_distance"],
            "hp": enemy["hp"],
            "hit_cooldown": 0.0,
            "blade_timers": {},
            "boss": enemy.get("boss", False),
        })


def _update_spawning(game, dt):
    spawn = game["spec"]["spawn"]
    game["spawn_timer"] += dt
    if game["spawn_timer"] < spawn["interval"]:
        return
    game["spawn_timer"] -= spawn["interval"]
    wave = current_wave(game["spec"], game["time"])
    if wave is None:
        return
    if wave.get("boss") and not game["boss_spawned"]:
        game["boss_spawned"] = True
        _spawn(game, "demon", 1)
    needed = min_alive(game["spec"], game["time"]) - len(game["enemies"])
    needed = min(needed, spawn["max_per_second"],
                 spawn["max_alive"] - len(game["enemies"]))
    for _ in range(max(0, needed)):
        _spawn(game, game["rng"].choice(wave["types"]), 1)


# ----------------------------------------------------------------------- hero

def _move_hero(game, dt):
    hero = game["hero"]
    target = game["target"]
    if target is None:
        return
    dx = target[0] - hero["x"]
    dy = target[1] - hero["y"]
    dist = math.hypot(dx, dy)
    if dist <= 0.0001:
        return
    hero["angle"] = math.atan2(dy, dx)
    move = hero_speed(game) * dt
    if dist <= move:
        hero["x"], hero["y"] = target
    else:
        hero["x"] += dx / dist * move
        hero["y"] += dy / dist * move


# -------------------------------------------------------------------- weapons

def _nearest_enemy(game):
    best = None
    best_d = None
    hx, hy = game["hero"]["x"], game["hero"]["y"]
    for enemy in game["enemies"]:
        d = (enemy["x"] - hx) ** 2 + (enemy["y"] - hy) ** 2
        if best_d is None or d < best_d:
            best, best_d = enemy, d
    return best


def _update_spark_wand(game, weapon, dt):
    cfg = wand_config(game["spec"], weapon["level"])
    weapon["cooldown"] -= dt
    if weapon["cooldown"] > 0:
        return
    weapon["cooldown"] += cfg["period"]
    target = _nearest_enemy(game)
    if target is None:
        return
    spec = game["spec"]
    straight = math.atan2(target["y"] - game["hero"]["y"],
                          target["x"] - game["hero"]["x"])
    for i in range(cfg["sparks"]):
        angle = straight + (i - (cfg["sparks"] - 1) / 2) * 0.15
        game["sparks"].append({
            "x": game["hero"]["x"],
            "y": game["hero"]["y"],
            "vx": math.cos(angle) * spec["spark_wand"]["speed"],
            "vy": math.sin(angle) * spec["spark_wand"]["speed"],
            "damage": cfg["damage"],
            "life": 2.0,
        })


def blade_positions(game, count):
    """Where the spin blades are now: one full turn every turn_period seconds."""
    spec = game["spec"]["spin_blades"]
    turn = game["time"] / spec["turn_period"] * TAU
    return [(game["hero"]["x"] + math.cos(turn + i * TAU / count) * spec["orbit_radius"],
             game["hero"]["y"] + math.sin(turn + i * TAU / count) * spec["orbit_radius"])
            for i in range(count)]


def _update_spin_blades(game, weapon, dt):
    spec = game["spec"]
    cfg = blades_config(spec, weapon["level"])
    blade_spec = spec["spin_blades"]
    for index, (bx, by) in enumerate(blade_positions(game, cfg["blades"])):
        for enemy in game["enemies"]:
            last = enemy["blade_timers"].get(index)
            if last is not None and game["time"] < last:
                continue
            reach = blade_spec["hit_radius"] + spec[enemy["kind"]]["radius"]
            if (enemy["x"] - bx) ** 2 + (enemy["y"] - by) ** 2 <= reach * reach:
                _hurt_enemy(game, enemy, cfg["damage"])
                enemy["blade_timers"][index] = game["time"] + blade_spec["hit_cooldown"]


def _update_holy_ring(game, weapon, dt):
    spec = game["spec"]
    cfg = ring_config(spec, weapon["level"])
    weapon["pulse"] = max(0.0, weapon["pulse"] - dt)
    weapon["cooldown"] -= dt
    if weapon["cooldown"] > 0:
        return
    weapon["cooldown"] += spec["holy_ring"]["period"]
    weapon["pulse"] = spec["holy_ring"]["pulse"]
    for enemy in game["enemies"]:
        reach = cfg["radius"] + spec[enemy["kind"]]["radius"]
        if (enemy["x"] - game["hero"]["x"]) ** 2 + (enemy["y"] - game["hero"]["y"]) ** 2 <= reach * reach:
            _hurt_enemy(game, enemy, cfg["damage"])


WEAPON_UPDATES = {
    "spark_wand": _update_spark_wand,
    "spin_blades": _update_spin_blades,
    "holy_ring": _update_holy_ring,
}


def _update_weapons(game, dt):
    for weapon in game["weapons"].values():
        update = WEAPON_UPDATES.get(weapon["kind"])
        if update:
            update(game, weapon, dt)


def _update_sparks(game, dt):
    spark_r = game["spec"]["spark_wand"]["radius"]
    for spark in game["sparks"]:
        spark["x"] += spark["vx"] * dt
        spark["y"] += spark["vy"] * dt
        spark["life"] -= dt
        for enemy in game["enemies"]:
            reach = spark_r + game["spec"][enemy["kind"]]["radius"]
            if (enemy["x"] - spark["x"]) ** 2 + (enemy["y"] - spark["y"]) ** 2 <= reach * reach:
                _hurt_enemy(game, enemy, spark["damage"])
                spark["life"] = 0.0
                break
    game["sparks"] = [s for s in game["sparks"] if s["life"] > 0]


# ------------------------------------------------- enemies, gems, death, XP

def _update_enemies(game, dt):
    spec = game["spec"]
    hero = game["hero"]
    for enemy in game["enemies"]:
        cfg = spec[enemy["kind"]]
        dx = hero["x"] - enemy["x"]
        dy = hero["y"] - enemy["y"]
        dist = math.hypot(dx, dy)
        if dist > 0.0001:
            move = cfg["speed"] * dt
            enemy["x"] += dx / dist * move
            enemy["y"] += dy / dist * move
        enemy["hit_cooldown"] -= dt
        if dist <= cfg["radius"] + spec["hero"]["hit_radius"] and enemy["hit_cooldown"] <= 0:
            enemy["hit_cooldown"] = cfg["contact_cooldown"]
            hero["hp"] -= cfg["damage"]
            _start_shake(game)
            _event(game, "hurt")
    kept = []
    for enemy in game["enemies"]:
        dist = math.hypot(enemy["x"] - hero["x"], enemy["y"] - hero["y"])
        if enemy["boss"]:
            # the boss is never removed: it is pulled back to the circle instead
            if dist > spec["spawn"]["boss_return_distance"]:
                angle = game["rng"].random() * TAU
                enemy["x"] = hero["x"] + math.cos(angle) * spec["spawn"]["circle_distance"]
                enemy["y"] = hero["y"] + math.sin(angle) * spec["spawn"]["circle_distance"]
            kept.append(enemy)
        elif dist <= spec["spawn"]["removal_distance"]:
            kept.append(enemy)
    game["enemies"] = kept
    if hero["hp"] <= 0:
        hero["hp"] = 0
        game["state"] = "lost"
        _event(game, "end")


def _collect_dead(game):
    """Remove dead enemies, count the kills and drop their XP as a gem."""
    spec = game["spec"]
    alive = []
    for enemy in game["enemies"]:
        if enemy["hp"] > 0:
            alive.append(enemy)
            continue
        game["kills"] += 1
        _add_flash(game, enemy)
        xp = spec[enemy["kind"]]["xp"]
        if xp:  # the boss is worth nothing
            game["gems"].append({"x": enemy["x"], "y": enemy["y"], "xp": xp})
    game["enemies"] = alive


def _update_gems(game, dt):
    spec = game["spec"]
    gem_spec = spec["gems"]
    hero = game["hero"]
    magnet = magnet_radius(game)
    reach = spec["hero"]["hit_radius"] + gem_spec["radius"]
    left = []
    for gem in game["gems"]:
        dx = hero["x"] - gem["x"]
        dy = hero["y"] - gem["y"]
        dist = math.hypot(dx, dy)
        if dist <= reach:
            game["xp"] += gem["xp"]
            _event(game, "gem")
            continue
        if dist <= magnet:
            move = gem_spec["speed"] * dt
            gem["x"] += dx / dist * move
            gem["y"] += dy / dist * move
        left.append(gem)
    game["gems"] = left


# ------------------------------------------------------------------ level up

def make_cards(game):
    """Three random cards: a new weapon, a level for something you have,
    or a passive item. Something already at level 5 is never offered."""
    spec = game["spec"]
    options = []
    for kind, item in spec["items"].items():
        if item["kind"] == "special":
            continue
        level = item_level(game, kind)
        if level >= item["max_level"]:
            continue
        if item["kind"] == "weapon" and level == 0 and len(game["weapons"]) >= spec["weapon_slots"]:
            continue
        options.append({"kind": kind, "level": level + 1})
    game["rng"].shuffle(options)
    cards = options[:spec["level_up"]["cards_shown"]]
    heal_card = {"kind": "heal", "level": 1}
    while len(cards) < spec["level_up"]["cards_shown"]:
        cards.append(dict(heal_card))
    return cards


def choose_card(game, index):
    """Take one of the level-up cards and start the game again."""
    if game["state"] != "levelup" or not 0 <= index < len(game["cards"]):
        return game
    spec = game["spec"]
    card = game["cards"][index]
    kind = card["kind"]
    if kind == "heal":
        heal(game, spec["level_up"]["heal_amount"])
    else:
        item = spec["items"][kind]
        level = item_level(game, kind) + 1
        if item["kind"] == "weapon":
            game["weapons"][kind] = (game["weapons"].get(kind) or new_weapon(kind, 0))
            game["weapons"][kind]["level"] = level
        else:
            game["passives"][kind] = {"level": level}
            if kind == "big_heart":
                game["hero"]["max_hp"] += spec["passives"]["big_heart"]["hp"]
                heal(game, spec["passives"]["big_heart"]["hp"])
    game["xp"] -= xp_needed(spec, game["level"])
    game["level"] += 1
    game["cards"] = []
    if game["xp"] >= xp_needed(spec, game["level"]):
        game["cards"] = make_cards(game)  # enough XP for the next level too
    else:
        game["state"] = "playing"
    return game


def _check_victory(game):
    """Survive until the goal time and the game is won."""
    goal = game["spec"]["victory"]["goal_time"]
    if game["state"] == "playing" and game["time"] >= goal:
        game["time"] = goal
        game["state"] = "won"
        _event(game, "end")
        return True
    return False


def _check_level_up(game):
    if game["state"] != "playing":
        return
    if game["xp"] >= xp_needed(game["spec"], game["level"]):
        game["state"] = "levelup"
        game["cards"] = make_cards(game)
        _event(game, "levelup")


# ---------------------------------------------------------------------- step

def step(game, dt):
    """Advance the game by dt seconds. Call with dt = 1/60, once per frame."""
    if game["state"] != "playing":
        return game
    game["time"] += dt
    _update_feel(game, dt)
    _move_hero(game, dt)
    _update_spawning(game, dt)
    _update_weapons(game, dt)
    _update_sparks(game, dt)
    _update_enemies(game, dt)
    _collect_dead(game)
    _update_gems(game, dt)
    if _check_victory(game):
        return game
    _check_level_up(game)
    return game
