"""Small unittest tests for the rules in rules.py (no window, no drawing)."""

import copy
import json
import math
import os
import random
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rules

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = json.load(open(os.path.join(HERE, "..", "data", "game.json"),
                      encoding="utf-8"))
STEP = 1.0 / SPEC["time"]["step"]


def make_game(spec=SPEC, seed=1):
    return rules.new_game(spec, rng=random.Random(seed))


def run(game, seconds):
    for _ in range(round(seconds / STEP)):
        rules.step(game, STEP)
    return game


def enemy(kind, x, y, hp=None):
    spec = SPEC[kind]
    return {"kind": kind, "x": x, "y": y,
            "hp": spec["hp"] if hp is None else hp,
            "hit_cooldown": 0, "blade_timers": {},
            "boss": spec.get("boss", False)}


def bat(x, y, hp=8):
    return enemy("bat", x, y, hp)


def still_spec():
    """The real numbers, but bats do not move or hurt: easy to measure against."""
    spec = copy.deepcopy(SPEC)
    spec["bat"]["speed"] = 0
    spec["bat"]["damage"] = 0
    spec["spawn"]["waves"] = []
    return spec


def invincible_spec():
    spec = copy.deepcopy(SPEC)
    for kind in ("bat", "slime", "ghost", "demon"):
        spec[kind]["damage"] = 0
    return spec


class Spawning(unittest.TestCase):
    def test_bats_appear_on_the_circle_around_the_hero(self):
        game = run(make_game(), 1.0)
        self.assertGreater(len(game["enemies"]), 0)
        for enemy in game["enemies"]:
            d = math.hypot(enemy["x"] - game["hero"]["x"],
                           enemy["y"] - game["hero"]["y"])
            self.assertGreaterEqual(d, SPEC["spawn"]["circle_distance"] - 5)

    def test_at_most_eight_new_enemies_per_second(self):
        game = run(make_game(), 1.0)
        self.assertLessEqual(len(game["enemies"]),
                             SPEC["spawn"]["max_per_second"])

    def test_never_more_than_the_max_alive(self):
        # a spec that wants far more enemies than the cap allows
        spec = copy.deepcopy(SPEC)
        spec["bat"]["damage"] = 0
        spec["spawn"]["waves"] = [{"from": 0, "types": ["bat"], "min_alive": 9999}]
        game = make_game(spec)
        game["weapons"] = {}  # no shooting, so the bats stay alive
        run(game, 20.0)
        self.assertEqual(len(game["enemies"]), spec["spawn"]["max_alive"])

    def test_enemies_far_from_the_hero_are_removed(self):
        game = make_game()
        game["weapons"] = {}
        far = SPEC["spawn"]["removal_distance"] + 400
        game["enemies"] = [bat(far, 0, hp=99999)]
        run(game, 1.0)
        self.assertEqual([e for e in game["enemies"] if e["hp"] == 99999], [])


class Hero(unittest.TestCase):
    def test_walks_toward_the_target_at_the_right_speed(self):
        game = make_game()
        game["target"] = (500, 0)
        run(game, 1.0)
        self.assertAlmostEqual(game["hero"]["x"], SPEC["hero"]["speed"], places=1)

    def test_walks_without_new_mouse_moves(self):
        game = make_game()
        game["target"] = (500, 0)
        run(game, 1.0)
        first = game["hero"]["x"]
        run(game, 1.0)
        self.assertAlmostEqual(game["hero"]["x"], first + SPEC["hero"]["speed"], places=1)

    def test_stops_at_the_target(self):
        game = make_game()
        game["target"] = (5, 5)
        run(game, 1.0)
        self.assertAlmostEqual(game["hero"]["x"], 5, places=6)
        self.assertAlmostEqual(game["hero"]["y"], 5, places=6)

    def test_the_map_has_no_edges(self):
        game = make_game()
        game["target"] = (-100000, -100000)
        run(game, 3.0)
        self.assertLess(game["hero"]["x"], -250)
        self.assertLess(game["hero"]["y"], -250)


class SparkWand(unittest.TestCase):
    def test_shoots_and_kills_a_bat(self):
        game = make_game()
        game["enemies"] = [bat(60, 0)]
        run(game, 0.5)  # before the first spawn second
        self.assertEqual(game["kills"], 1)
        self.assertEqual(len(game["enemies"]), 0)

    def test_aims_at_the_nearest_enemy(self):
        game = make_game()
        game["enemies"] = [bat(-300, 0, hp=9999), bat(50, 0, hp=9999)]
        rules.step(game, STEP)  # the wand shoots on the first step
        self.assertEqual(len(game["sparks"]), 1)
        self.assertGreater(game["sparks"][0]["vx"], 0)

    def test_level_3_adds_a_spark_and_more_damage(self):
        level_1 = rules.wand_config(SPEC, 1)
        level_3 = rules.wand_config(SPEC, 3)
        self.assertEqual(level_1["sparks"], 1)
        self.assertEqual(level_3["sparks"], 2)
        self.assertEqual(level_3["damage"],
                         10 + 2 * SPEC["spark_wand"]["extra_level"]["damage"])
        self.assertAlmostEqual(level_3["period"],
                               0.8 - 2 * SPEC["spark_wand"]["extra_level"]["period"])


class DamageAndLosing(unittest.TestCase):
    def test_contact_damage_once_every_cooldown(self):
        game = make_game()
        bat_spec = SPEC["bat"]
        hero_spec = SPEC["hero"]
        game["enemies"] = [bat(0, 0, hp=99999)]
        rules.step(game, STEP)
        self.assertEqual(game["hero"]["hp"], hero_spec["hp"] - bat_spec["damage"])
        run(game, bat_spec["contact_cooldown"] - 0.2)
        self.assertEqual(game["hero"]["hp"], hero_spec["hp"] - bat_spec["damage"])
        run(game, 0.3)
        self.assertEqual(game["hero"]["hp"], hero_spec["hp"] - 2 * bat_spec["damage"])

    def test_game_over_when_hp_reaches_zero(self):
        game = make_game()
        game["enemies"] = [bat(0, 0, hp=99999)]
        hits = math.ceil(SPEC["hero"]["hp"] / SPEC["bat"]["damage"]) + 2
        run(game, hits * SPEC["bat"]["contact_cooldown"] + 1)
        self.assertEqual(game["state"], "lost")
        self.assertEqual(game["hero"]["hp"], 0)

    def test_nothing_moves_after_the_game_is_lost(self):
        game = make_game()
        game["state"] = "lost"
        run(game, 2.0)
        self.assertEqual(game["time"], 0.0)
        self.assertEqual(game["enemies"], [])


class GemsAndXp(unittest.TestCase):
    def test_a_dead_bat_drops_a_gem_worth_its_xp(self):
        game = make_game(still_spec())
        game["enemies"] = [bat(200, 0)]  # far away, so the gem is not pulled in
        run(game, 0.6)
        self.assertEqual(game["kills"], 1)
        self.assertEqual(len(game["gems"]), 1)
        self.assertEqual(game["gems"][0]["xp"], SPEC["bat"]["xp"])
        self.assertEqual(game["xp"], 0)  # it is still lying on the floor

    def test_a_gem_inside_the_magnet_radius_flys_to_the_hero(self):
        game = make_game(still_spec())
        game["weapons"] = {}
        game["gems"] = [{"x": 50, "y": 0, "xp": 1}]
        run(game, 0.1)
        self.assertLess(game["gems"][0]["x"], 50)

    def test_a_gem_outside_the_magnet_radius_stays_where_it_is(self):
        game = make_game(still_spec())
        game["weapons"] = {}
        far = SPEC["hero"]["magnet_radius"] + 40
        game["gems"] = [{"x": far, "y": 0, "xp": 1}]
        run(game, 0.5)
        self.assertAlmostEqual(game["gems"][0]["x"], far)

    def test_reaching_the_hero_the_gem_adds_its_xp(self):
        game = make_game(still_spec())
        game["weapons"] = {}
        game["gems"] = [{"x": 5, "y": 0, "xp": 1}]
        run(game, 0.1)
        self.assertEqual(game["gems"], [])
        self.assertEqual(game["xp"], 1)

    def test_the_xp_needed_for_the_next_level(self):
        needed = [rules.xp_needed(SPEC, level) for level in (1, 2, 3, 4)]
        self.assertEqual(needed, [5, 8, 11, 14])

    def test_the_magnet_item_widens_the_pull(self):
        game = make_game()
        base = rules.magnet_radius(game)
        game["passives"]["magnet"] = {"level": 2}
        self.assertEqual(rules.magnet_radius(game),
                         base + 2 * SPEC["passives"]["magnet"]["radius"])


class LevelUp(unittest.TestCase):
    def level_up_game(self, xp):
        game = make_game(still_spec())
        game["weapons"] = {}
        game["gems"] = [{"x": 5, "y": 0, "xp": xp}]
        run(game, 0.1)
        return game

    def test_enough_xp_pauses_the_game_with_three_cards(self):
        game = self.level_up_game(SPEC["xp"]["first_level"])
        self.assertEqual(game["state"], "levelup")
        self.assertEqual(len(game["cards"]), SPEC["level_up"]["cards_shown"])
        self.assertEqual(game["level"], 1)
        stopped = game["time"]
        run(game, 2.0)
        self.assertEqual(game["time"], stopped)  # nothing moves while you choose

    def test_choosing_a_card_starts_the_game_again(self):
        game = self.level_up_game(SPEC["xp"]["first_level"])
        game["cards"] = [{"kind": "spin_blades", "level": 1},
                         {"kind": "magnet", "level": 1},
                         {"kind": "heal", "level": 1}]
        rules.choose_card(game, 0)
        self.assertEqual(game["state"], "playing")
        self.assertEqual(game["level"], 2)
        self.assertEqual(game["xp"], 0)
        self.assertEqual(game["weapons"]["spin_blades"]["level"], 1)
        self.assertEqual(game["passives"], {})

    def test_two_level_ups_at_once_ask_for_cards_twice(self):
        game = self.level_up_game(20)  # enough for level 2 and level 3
        self.assertEqual(game["state"], "levelup")
        rules.choose_card(game, 0)
        self.assertEqual(game["level"], 2)
        self.assertEqual(game["state"], "levelup")  # still cards to choose
        self.assertEqual(len(game["cards"]), 3)

    def test_a_card_you_already_have_goes_up_one_level(self):
        game = make_game(still_spec())
        game["state"] = "levelup"
        game["xp"] = rules.xp_needed(SPEC, 1)
        game["cards"] = [{"kind": "spark_wand", "level": 2}]
        rules.choose_card(game, 0)
        self.assertEqual(game["weapons"]["spark_wand"]["level"], 2)

    def test_the_heal_card_heals_but_never_over_the_max(self):
        game = self.level_up_game(SPEC["xp"]["first_level"])
        game["hero"]["hp"] = game["hero"]["max_hp"] - 5
        game["cards"] = [{"kind": "heal", "level": 1}]
        rules.choose_card(game, 0)
        self.assertEqual(game["hero"]["hp"], game["hero"]["max_hp"])

    def test_a_bad_choice_does_nothing(self):
        game = self.level_up_game(SPEC["xp"]["first_level"])
        cards = game["cards"]
        rules.choose_card(game, 9)
        self.assertEqual(game["cards"], cards)
        self.assertEqual(game["state"], "levelup")

    def test_the_cards_are_three_different_things(self):
        game = make_game()
        for _ in range(30):
            kinds = [card["kind"] for card in rules.make_cards(game)]
            self.assertEqual(len(kinds), len(set(kinds)))

    def test_nothing_at_level_5_is_ever_offered(self):
        game = make_game()
        game["weapons"]["spark_wand"]["level"] = SPEC["items"]["spark_wand"]["max_level"]
        for _ in range(30):
            kinds = [card["kind"] for card in rules.make_cards(game)]
            self.assertNotIn("spark_wand", kinds)

    def test_no_fourth_weapon_when_you_already_have_three(self):
        game = make_game()
        game["weapons"]["spin_blades"] = rules.new_weapon("spin_blades", 1)
        game["weapons"]["holy_ring"] = rules.new_weapon("holy_ring", 1)
        self.assertEqual(len(game["weapons"]), SPEC["weapon_slots"])
        for _ in range(30):
            for card in rules.make_cards(game):
                if SPEC["items"][card["kind"]]["kind"] == "weapon":
                    # only an upgrade of a weapon you carry, never a new one
                    self.assertIn(card["kind"], game["weapons"])

    def test_when_nothing_is_left_the_cards_heal(self):
        game = make_game()
        for kind, item in SPEC["items"].items():
            if item["kind"] == "weapon":
                game["weapons"][kind] = rules.new_weapon(kind, item["max_level"])
            elif item["kind"] == "passive":
                game["passives"][kind] = {"level": item["max_level"]}
        cards = rules.make_cards(game)
        self.assertEqual([card["kind"] for card in cards],
                         ["heal"] * SPEC["level_up"]["cards_shown"])


class SpinBlades(unittest.TestCase):
    def blades_game(self, level=1, cooldown=None):
        spec = still_spec()
        if cooldown is not None:
            spec["spin_blades"]["hit_cooldown"] = cooldown
        game = make_game(spec)
        game["weapons"] = {"spin_blades": rules.new_weapon("spin_blades", level)}
        return game

    def test_more_blades_and_more_damage_at_higher_levels(self):
        blades = [rules.blades_config(SPEC, level)["blades"] for level in (1, 2, 3, 4, 5)]
        self.assertEqual(blades, [2, 3, 3, 4, 4])
        self.assertEqual(rules.blades_config(SPEC, 5)["damage"],
                         8 + 4 * SPEC["spin_blades"]["extra_level"]["damage"])

    def test_the_blades_are_evenly_spaced_on_their_circle(self):
        game = self.blades_game(level=1)
        positions = rules.blade_positions(game, 2)
        for x, y in positions:
            self.assertAlmostEqual(math.hypot(x, y),
                                   SPEC["spin_blades"]["orbit_radius"], places=6)

    def test_a_blade_hurts_an_enemy_it_passes_through(self):
        game = self.blades_game()
        enemy = bat(SPEC["spin_blades"]["orbit_radius"], 0, hp=99999)
        game["enemies"] = [enemy]
        run(game, 3.0)
        self.assertLess(enemy["hp"], 99999)
        self.assertEqual((99999 - enemy["hp"]) % rules.blades_config(SPEC, 1)["damage"], 0)

    def test_one_blade_hits_the_same_enemy_at_most_every_half_second(self):
        enemy_hp = 999999
        slow = self.blades_game()
        enemy = bat(SPEC["spin_blades"]["orbit_radius"], 0, hp=enemy_hp)
        slow["enemies"] = [enemy]
        run(slow, 3.0)
        hits_with_cooldown = (enemy_hp - enemy["hp"]) // 8

        fast = self.blades_game(cooldown=-1)  # no cooldown at all
        enemy2 = bat(SPEC["spin_blades"]["orbit_radius"], 0, hp=enemy_hp)
        fast["enemies"] = [enemy2]
        run(fast, 3.0)
        hits_without_cooldown = (enemy_hp - enemy2["hp"]) // 8

        self.assertGreater(hits_with_cooldown, 0)
        self.assertGreater(hits_without_cooldown, 3 * hits_with_cooldown)


class HolyRing(unittest.TestCase):
    def test_the_ring_hurts_every_enemy_inside_it_and_nobody_outside(self):
        game = make_game(still_spec())
        game["weapons"] = {"holy_ring": rules.new_weapon("holy_ring", 1)}
        damage = SPEC["holy_ring"]["level_1"]["damage"]
        inside = [bat(30, 0, hp=9999), bat(0, 45, hp=9999)]
        outside = bat(SPEC["holy_ring"]["level_1"]["radius"] + 60, 0, hp=9999)
        game["enemies"] = inside + [outside]
        run(game, 1.0)  # the ring fires every 0.5 s
        for enemy in inside:
            hurt = 9999 - enemy["hp"]
            self.assertGreaterEqual(hurt, 2 * damage)
            self.assertEqual(hurt % damage, 0)
        self.assertEqual(outside["hp"], 9999)

    def test_the_ring_grows_and_hurts_harder_each_level(self):
        level_1 = rules.ring_config(SPEC, 1)
        level_5 = rules.ring_config(SPEC, 5)
        self.assertEqual(level_5["radius"],
                         level_1["radius"] + 4 * SPEC["holy_ring"]["extra_level"]["radius"])
        self.assertEqual(level_5["damage"],
                         level_1["damage"] + 4 * SPEC["holy_ring"]["extra_level"]["damage"])


class PassiveItems(unittest.TestCase):
    def choose(self, kind, level=1):
        game = make_game(still_spec())
        game["weapons"] = {}
        game["cards"] = [{"kind": kind, "level": level},
                         {"kind": "heal", "level": 1},
                         {"kind": "heal", "level": 1}]
        game["xp"] = rules.xp_needed(SPEC, game["level"])
        game["state"] = "levelup"
        return rules.choose_card(game, 0)

    def test_swift_boots_make_the_hero_walk_faster(self):
        game = make_game()
        self.assertAlmostEqual(rules.hero_speed(game), SPEC["hero"]["speed"])
        game["passives"]["swift_boots"] = {"level": 3}
        self.assertAlmostEqual(rules.hero_speed(game),
                               SPEC["hero"]["speed"] * 1.3)

    def test_swift_boots_really_move_the_hero_further(self):
        game = self.choose("swift_boots")
        game["target"] = (500, 0)
        run(game, 1.0)
        self.assertAlmostEqual(game["hero"]["x"],
                               SPEC["hero"]["speed"] * 1.1, places=1)

    def test_big_heart_adds_max_hp_and_heals(self):
        game = self.choose("big_heart")
        self.assertEqual(game["hero"]["max_hp"],
                         SPEC["hero"]["hp"] + SPEC["passives"]["big_heart"]["hp"])
        self.assertEqual(game["hero"]["hp"], game["hero"]["max_hp"])

    def test_magnet_item_is_offered_and_applied(self):
        game = self.choose("magnet")
        self.assertEqual(game["passives"]["magnet"]["level"], 1)
        self.assertEqual(rules.magnet_radius(game),
                         SPEC["hero"]["magnet_radius"] + SPEC["passives"]["magnet"]["radius"])


class TheWaveTable(unittest.TestCase):
    def test_the_table_says_who_comes_when(self):
        at = lambda t: rules.current_wave(SPEC, t)["types"]
        self.assertEqual(at(0), ["bat"])
        self.assertEqual(at(29.9), ["bat"])
        self.assertEqual(at(30), ["bat", "slime"])
        self.assertEqual(at(45), ["slime", "ghost"])
        self.assertEqual(at(60), ["bat", "ghost"])
        self.assertEqual(at(75), ["bat", "slime", "ghost"])
        self.assertEqual(at(90), ["bat", "slime"])
        self.assertEqual(at(105), ["bat"])

    def test_the_minimum_alive_grows_with_time(self):
        times = [wave["from"] for wave in SPEC["spawn"]["waves"]]
        mins = [wave["min_alive"] for wave in SPEC["spawn"]["waves"]]
        self.assertEqual([rules.min_alive(SPEC, t) for t in times], mins)
        self.assertEqual(mins, [12, 20, 28, 36, 45, 55, 55, 75])

    def test_only_bats_come_in_the_first_seconds(self):
        game = make_game(invincible_spec())
        game["weapons"] = {}  # nothing dies, so the counts are plain
        run(game, 3.0)
        self.assertEqual({e["kind"] for e in game["enemies"]}, {"bat"})
        self.assertEqual(len(game["enemies"]), SPEC["spawn"]["waves"][0]["min_alive"])

    def test_slimes_join_in_from_half_past_the_minute(self):
        game = make_game(invincible_spec())
        game["weapons"] = {}  # nothing dies, so everything that came stays
        run(game, 33.0)
        kinds = {e["kind"] for e in game["enemies"]}
        self.assertEqual(kinds, {"bat", "slime"})

    def test_the_hero_survives_the_two_minutes_of_the_table(self):
        spec = invincible_spec()
        game = make_game(spec)
        game["weapons"] = {}
        for _ in range(round(120 / STEP) + 5):
            rules.step(game, STEP)
            self.assertLessEqual(len(game["enemies"]), spec["spawn"]["max_alive"])
        self.assertEqual(game["state"], "won")
        self.assertEqual(game["time"], spec["victory"]["goal_time"])


class TheBoss(unittest.TestCase):
    def test_the_boss_appears_once_at_one_thirty(self):
        spec = invincible_spec()
        game = make_game(spec)
        game["weapons"] = {}
        run(game, 89.0)
        self.assertEqual([e for e in game["enemies"] if e["boss"]], [])
        run(game, 3.0)
        bosses = [e for e in game["enemies"] if e["boss"]]
        self.assertEqual(len(bosses), 1)
        self.assertEqual(bosses[0]["kind"], "demon")
        self.assertEqual(bosses[0]["hp"], spec["demon"]["hp"])
        run(game, 20.0)
        self.assertEqual(len([e for e in game["enemies"] if e["boss"]]), 1)

    def test_the_boss_is_pulled_back_instead_of_being_removed(self):
        spec = invincible_spec()
        game = make_game(spec)
        game["weapons"] = {}
        far = spec["spawn"]["boss_return_distance"] + 200
        game["enemies"] = [enemy("demon", far, 0)]
        rules.step(game, STEP)
        boss = game["enemies"][0]
        dist = math.hypot(boss["x"] - game["hero"]["x"], boss["y"] - game["hero"]["y"])
        self.assertAlmostEqual(dist, spec["spawn"]["circle_distance"], places=6)

    def test_a_normal_enemy_still_walks_away_and_is_removed(self):
        game = make_game(still_spec())
        game["weapons"] = {}
        far = SPEC["spawn"]["removal_distance"] + 10
        game["enemies"] = [enemy("bat", far, 0)]
        rules.step(game, STEP)
        self.assertEqual(game["enemies"], [])

    def test_the_boss_is_worth_no_xp(self):
        game = make_game(still_spec())
        game["weapons"] = {}
        boss = enemy("demon", 100, 0, hp=1)
        game["enemies"] = [boss]
        boss["hp"] = 0
        rules.step(game, STEP)
        self.assertEqual(game["kills"], 1)
        self.assertEqual(game["gems"], [])

    def test_the_boss_hurts_hard(self):
        spec = copy.deepcopy(SPEC)
        spec["spawn"]["waves"] = []
        game = make_game(spec)
        game["weapons"] = {}
        game["enemies"] = [enemy("demon", 0, 0)]
        rules.step(game, STEP)
        self.assertEqual(game["hero"]["hp"],
                         spec["hero"]["hp"] - spec["demon"]["damage"])


class EnemyTypes(unittest.TestCase):
    def test_each_kind_uses_its_own_numbers(self):
        for kind in ("bat", "slime", "ghost"):
            spec = copy.deepcopy(SPEC)
            spec["spawn"]["waves"] = []
            game = make_game(spec)
            game["weapons"] = {}
            game["enemies"] = [enemy(kind, 300, 0)]
            run(game, 1.0)
            moved = 300 - game["enemies"][0]["x"]
            self.assertAlmostEqual(moved, spec[kind]["speed"], places=1)

    def test_a_ghost_is_faster_than_the_hero(self):
        self.assertGreater(SPEC["ghost"]["speed"], SPEC["hero"]["speed"])

    def test_a_slime_drops_a_gem_worth_two_xp(self):
        spec = copy.deepcopy(SPEC)
        spec["spawn"]["waves"] = []
        game = make_game(spec)
        game["weapons"] = {"holy_ring": rules.new_weapon("holy_ring", 5)}
        game["enemies"] = [enemy("slime", 40, 0, hp=1)]
        rules.step(game, STEP)  # the ring fires on the very first step
        self.assertEqual(game["kills"], 1)
        self.assertEqual([gem["xp"] for gem in game["gems"]], [spec["slime"]["xp"]])
        self.assertEqual(game["xp"], 0)


class Winning(unittest.TestCase):
    def test_surviving_to_the_goal_time_wins(self):
        game = make_game(still_spec())
        game["time"] = SPEC["victory"]["goal_time"] - 0.1
        run(game, 0.2)
        self.assertEqual(game["state"], "won")
        self.assertEqual(game["time"], SPEC["victory"]["goal_time"])
        run(game, 2.0)
        self.assertEqual(game["time"], SPEC["victory"]["goal_time"])

    def test_dying_on_the_last_second_is_still_game_over(self):
        spec = copy.deepcopy(SPEC)
        spec["spawn"]["waves"] = []
        game = make_game(spec)
        game["weapons"] = {}
        game["hero"]["hp"] = 1
        game["time"] = spec["victory"]["goal_time"] - 0.01
        game["enemies"] = [enemy("bat", 0, 0, hp=9999)]
        run(game, 0.1)
        self.assertEqual(game["state"], "lost")


class Feel(unittest.TestCase):
    """Damage numbers, the death flash, the screen shake and the sound events."""

    def setUp(self):
        self.feel = SPEC["feel"]

    def game_with_one_bat(self, hp=30, x=100):
        game = make_game(still_spec())
        game["enemies"] = [bat(x, 0, hp)]
        return game

    def test_a_hit_leaves_a_damage_number(self):
        game = self.game_with_one_bat()
        run(game, 0.3)
        self.assertEqual(len(game["floaters"]), 1)
        number = game["floaters"][0]
        self.assertEqual(number["amount"], SPEC["spark_wand"]["level_1"]["damage"])
        self.assertAlmostEqual(number["x"], 100)
        self.assertGreater(number["life"], 0)
        self.assertLessEqual(number["life"], self.feel["number_time"])

    def test_the_number_is_gone_after_a_while(self):
        game = self.game_with_one_bat()
        run(game, 0.3)
        self.assertTrue(game["floaters"])
        game["enemies"] = []
        run(game, self.feel["number_time"])
        self.assertEqual(game["floaters"], [])

    def test_only_a_limited_amount_of_numbers_is_shown(self):
        game = make_game(still_spec())
        game["weapons"] = {"holy_ring": rules.new_weapon("holy_ring", 5)}
        game["enemies"] = [bat(x, 0, hp=999) for x in range(-90, 91, 5)]
        run(game, 0.2)
        self.assertGreater(len(game["enemies"]), self.feel["max_numbers"])
        self.assertEqual(len(game["floaters"]), self.feel["max_numbers"])

    def test_a_dead_enemy_leaves_a_flash(self):
        game = self.game_with_one_bat(hp=1)
        run(game, 0.3)
        self.assertEqual(game["kills"], 1)
        self.assertEqual(len(game["flashes"]), 1)
        flash = game["flashes"][0]
        self.assertAlmostEqual(flash["x"], 100)
        self.assertEqual(flash["radius"], SPEC["bat"]["radius"])

    def test_the_flash_is_gone_after_a_while(self):
        game = self.game_with_one_bat(hp=1)
        run(game, 0.3 + self.feel["flash_time"])
        self.assertEqual(game["flashes"], [])

    def test_being_hurt_starts_a_shake(self):
        game = make_game()
        game["enemies"] = [bat(15, 0)]
        rules.step(game, STEP)
        self.assertAlmostEqual(game["shake"], self.feel["shake_time"], places=6)

    def test_the_shake_counts_down_to_zero_and_stops_there(self):
        game = make_game(still_spec())
        game["shake"] = 0.01
        run(game, 1.0)
        self.assertEqual(game["shake"], 0.0)

    def test_the_sounds_have_their_own_event(self):
        game = self.game_with_one_bat()
        run(game, 0.3)
        self.assertIn("hit", game["events"])

        game = make_game(still_spec())
        game["gems"] = [{"x": 5, "y": 0, "xp": 1}]
        rules.step(game, STEP)
        self.assertIn("gem", game["events"])

        game = make_game(still_spec())
        game["xp"] = rules.xp_needed(SPEC, 1)
        rules.step(game, STEP)
        self.assertIn("levelup", game["events"])

        game = make_game(still_spec())
        game["time"] = SPEC["victory"]["goal_time"]
        rules.step(game, STEP)
        self.assertEqual(game["state"], "won")
        self.assertEqual(game["events"].count("end"), 1)

    def test_losing_the_game_sends_hurt_and_end(self):
        game = make_game()
        game["hero"]["hp"] = 3
        game["enemies"] = [bat(15, 0)]
        run(game, 0.1)
        self.assertEqual(game["state"], "lost")
        self.assertIn("hurt", game["events"])
        self.assertEqual(game["events"].count("end"), 1)

    def test_a_dead_hero_does_not_get_cards(self):
        game = make_game()
        game["hero"]["hp"] = 3
        game["xp"] = rules.xp_needed(SPEC, 1)  # enough XP in the same second
        game["enemies"] = [bat(15, 0)]
        run(game, 0.1)
        self.assertEqual(game["state"], "lost")


if __name__ == "__main__":
    unittest.main()
