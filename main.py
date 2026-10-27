"""Night Survivors - window, drawing, sound and input.

The game rules live in rules.py; this file only draws the state with the
pictures in assets/, plays the sounds in sounds/ and feeds the rules the
mouse or finger position. Run make_assets.py and make_sounds.py once before
this file, or it will tell you to.
"""

import asyncio
import json
import math
import os

import pygame

import rules

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "data", "game.json"), encoding="utf-8") as handle:
    SPEC = json.load(handle)

STEP = 1.0 / SPEC["time"]["step"]

# The pictures made by make_assets.py
ASSET_NAMES = ["hero", "bat", "slime", "ghost", "demon", "floor", "sword",
               "gem_blue", "gem_pink"]
IMAGES = {}

# The sounds made by make_sounds.py, and the last time each one was played
SOUND_NAMES = ["hit", "gem", "levelup", "hurt", "end"]
SOUNDS = {}
LAST_PLAYED = {}

# Colours (only for the parts that are still shapes)
SHADOW = (30, 26, 24)
SPARK_FILL = (255, 236, 120)
SPARK_EDGE = (255, 150, 40)
RING_FILL = (255, 232, 150)
RING_EDGE = (255, 200, 90)
HP_BACK = (58, 34, 38)
HP_BAR = (225, 80, 80)
XP_BACK = (30, 44, 74)
XP_BAR = (90, 160, 250)
CARD_BACK = (38, 42, 52)
CARD_EDGE = (200, 180, 110)
CARD_NAME = (255, 226, 140)
NUMBER_TEXT = (255, 245, 200)
FLASH = (255, 255, 255)
TEXT = (250, 250, 250)
TEXT_SHADE = (28, 30, 36)
OVERLAY = (20, 22, 28)

# the two ways a run ends
ENDED = ("lost", "won")


def load_font(size):
    return pygame.font.Font(None, size)


def load_images():
    """Read the finished pictures from assets/ into IMAGES."""
    missing = [n + ".png" for n in ASSET_NAMES
               if not os.path.exists(os.path.join(HERE, "assets", n + ".png"))]
    if missing:
        raise SystemExit("Missing pictures: " + ", ".join(missing)
                         + "\nRun this once first:  python make_assets.py")
    for name in ASSET_NAMES:
        path = os.path.join(HERE, "assets", name + ".png")
        image = pygame.image.load(path).convert_alpha()
        IMAGES[name] = image
        if name == "floor" and image.get_width() != SPEC["world"]["tile"]:
            raise SystemExit(
                f"assets/floor.png is {image.get_width()} px but "
                f'data/game.json says "world.tile" is {SPEC["world"]["tile"]}. '
                "Make them the same number.")
    return IMAGES


def load_sounds():
    """Read the finished sounds from sounds/ into SOUNDS.

    A sound can be .ogg or .wav: whichever file is there gets used, because a
    web browser is picky about the format. If the browser refuses one, the
    game still runs; only that sound is missing.
    """
    missing = []
    for name in SOUND_NAMES:
        for ext in (".ogg", ".wav"):
            path = os.path.join(HERE, "sounds", name + ext)
            if not os.path.exists(path):
                continue
            try:
                sound = pygame.mixer.Sound(path)
            except (pygame.error, RuntimeError) as error:
                print(f"This browser cannot play {os.path.basename(path)}: {error}")
                break
            sound.set_volume(SPEC["sounds"]["volume"])
            SOUNDS[name] = sound
            break
        else:
            missing.append(name + ".wav")
    if missing:
        raise SystemExit("Missing sounds: " + ", ".join(missing)
                         + "\nRun this once first:  python make_sounds.py")
    return SOUNDS


def play(name):
    """Play one of the game sounds. The same sound never plays twice in a row."""
    sound = SOUNDS.get(name)
    if sound is None:
        return
    now = pygame.time.get_ticks() / 1000.0
    if now - LAST_PLAYED.get(name, -1.0) < SPEC["sounds"]["same_gap"]:
        return
    LAST_PLAYED[name] = now
    sound.play()


def camera(game):
    """Where the top left corner of the screen is in the world, shake included."""
    w = pygame.display.get_surface().get_width()
    h = pygame.display.get_surface().get_height()
    ox, oy = shake_offset(game)
    return game["hero"]["x"] - w / 2 + ox, game["hero"]["y"] - h / 2 + oy


def shake_offset(game):
    """The camera is pulled a few pixels aside while the shake timer runs down."""
    if game["shake"] <= 0:
        return 0.0, 0.0
    feel = SPEC["feel"]
    strength = feel["shake_pixels"] * game["shake"] / feel["shake_time"]
    t = game["time"] * 55
    return math.sin(t) * strength, math.cos(t * 1.7) * strength


def world_to_screen(game, x, y):
    left, top = camera(game)
    return x - left, y - top


def screen_to_world(game, x, y):
    w = pygame.display.get_surface().get_width()
    h = pygame.display.get_surface().get_height()
    return x - w / 2 + game["hero"]["x"], y - h / 2 + game["hero"]["y"]


def draw_floor(s, game):
    """Repeat the one floor tile over the whole visible area, forever."""
    tile = IMAGES["floor"]
    size = tile.get_width()
    left, top = camera(game)
    for iy in range(math.floor(top / size), math.floor((top + s.get_height()) / size) + 1):
        for ix in range(math.floor(left / size), math.floor((left + s.get_width()) / size) + 1):
            s.blit(tile, (ix * size - left, iy * size - top))


def draw_shadow(s, x, y, r):
    pygame.draw.ellipse(s, SHADOW, (x - r, y - r * 0.4, r * 2, r * 0.8))


def draw_sprite(s, game, image, x, y, scale=1, shadow=0):
    """Draw one picture with its middle at this world position."""
    sx, sy = world_to_screen(game, x, y)
    if scale != 1:
        image = pygame.transform.scale(image, (image.get_width() * scale,
                                               image.get_height() * scale))
    w, h = image.get_size()
    if shadow:
        draw_shadow(s, sx, sy + h / 2 - shadow, shadow)
    s.blit(image, (sx - w / 2, sy - h / 2))


def draw_enemy(s, game, enemy):
    cfg = SPEC[enemy["kind"]]
    draw_sprite(s, game, IMAGES[enemy["kind"]], enemy["x"], enemy["y"],
                scale=cfg.get("draw_scale", 1), shadow=cfg["radius"])


def draw_hero(s, game):
    draw_sprite(s, game, IMAGES["hero"], game["hero"]["x"], game["hero"]["y"],
                shadow=SPEC["hero"]["hit_radius"])


def draw_spark(s, game, spark):
    x, y = world_to_screen(game, spark["x"], spark["y"])
    r = SPEC["spark_wand"]["radius"]
    pygame.draw.circle(s, SPARK_FILL, (x, y), r)
    pygame.draw.circle(s, SPARK_EDGE, (x, y), r, 1)


def draw_gem(s, game, gem):
    name = "gem_blue" if gem["xp"] <= 1 else "gem_pink"
    draw_sprite(s, game, IMAGES[name], gem["x"], gem["y"])


def draw_blades(s, game, weapon):
    cfg = rules.blades_config(SPEC, weapon["level"])
    hero = game["hero"]
    for bx, by in rules.blade_positions(game, cfg["blades"]):
        angle = math.atan2(by - hero["y"], bx - hero["x"])
        # sword.png points up, so turn it to point away from the hero
        image = pygame.transform.rotate(IMAGES["sword"],
                                        -(math.degrees(angle) + 90))
        sx, sy = world_to_screen(game, bx, by)
        s.blit(image, image.get_rect(center=(sx, sy)))


def draw_ring(s, game, weapon):
    """The ring lights up for a moment every time it hurts the enemies."""
    if weapon["pulse"] <= 0:
        return
    cfg = rules.ring_config(SPEC, weapon["level"])
    r = cfg["radius"]
    strength = weapon["pulse"] / SPEC["holy_ring"]["pulse"]
    size = int(r * 2) + 6
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    centre = (size // 2, size // 2)
    pygame.draw.circle(surface, (*RING_FILL, int(50 * strength)), centre, r)
    pygame.draw.circle(surface, (*RING_EDGE, int(255 * strength)), centre, r, 3)
    sx, sy = world_to_screen(game, game["hero"]["x"], game["hero"]["y"])
    s.blit(surface, (sx - size / 2, sy - size / 2))


def draw_effects(s, game):
    ring = game["weapons"].get("holy_ring")
    if ring:
        draw_ring(s, game, ring)
    for gem in game["gems"]:
        draw_gem(s, game, gem)
    draw_hero(s, game)
    blades = game["weapons"].get("spin_blades")
    if blades:
        draw_blades(s, game, blades)
    for spark in game["sparks"]:
        draw_spark(s, game, spark)


def draw_flashes(s, game):
    """A white burst that grows and fades where an enemy just died."""
    feel = SPEC["feel"]
    for item in game["flashes"]:
        rest = item["life"] / feel["flash_time"]  # 1 at the start, 0 at the end
        radius = item["radius"] * (1.0 + (1.0 - rest) * 0.4)
        size = int(radius * 2) + 4
        overlay = pygame.Surface((size, size), pygame.SRCALPHA)
        centre = (size // 2, size // 2)
        pygame.draw.circle(overlay, (*FLASH, int(110 * rest)), centre, radius)
        pygame.draw.circle(overlay, (*FLASH, int(200 * rest)), centre, radius, 2)
        x, y = world_to_screen(game, item["x"], item["y"])
        s.blit(overlay, (x - size / 2, y - size / 2))


NUMBER_IMAGES = {}


def number_image(font, amount):
    """One damage number as a small picture. Made once per number, then reused."""
    key = str(amount)
    image = NUMBER_IMAGES.get(key)
    if image is None:
        text = font.render(key, True, NUMBER_TEXT)
        shade = font.render(key, True, TEXT_SHADE)
        image = pygame.Surface((text.get_width() + 2, text.get_height() + 2),
                               pygame.SRCALPHA)
        image.blit(shade, (2, 2))
        image.blit(text, (1, 1))
        NUMBER_IMAGES[key] = image
    return image


def draw_numbers(s, game, font):
    """The damage numbers: they float up and fade out at the end."""
    feel = SPEC["feel"]
    for item in game["floaters"]:
        image = number_image(font, item["amount"])
        image.set_alpha(int(255 * min(1.0, item["life"] / 0.15)))
        x, y = world_to_screen(game, item["x"], item["y"])
        y -= (1.0 - item["life"] / feel["number_time"]) * feel["number_rise"]
        s.blit(image, (x - image.get_width() / 2, y - image.get_height()))


def draw_text(s, font, text, pos, colour=TEXT, anchor="topleft"):
    """Text with a dark copy behind it, so it stays readable on the floor."""
    image = font.render(text, True, colour)
    shade = font.render(text, True, TEXT_SHADE)
    rect = image.get_rect(**{anchor: pos})
    s.blit(shade, (rect.x + 1, rect.y + 1))
    s.blit(image, rect)


def fmt_time(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def inventory_text(game):
    """What you have, for example "Spark 2  Blades 1  Boots 1"."""
    parts = []
    for kind, item in SPEC["items"].items():
        level = rules.item_level(game, kind)
        if level:
            parts.append(f"{item['short']} {level}")
    return "  ".join(parts)


def draw_bar(s, x, y, w, h, ratio, back, fill):
    pygame.draw.rect(s, back, (x, y, w, h), border_radius=4)
    if ratio > 0:
        pygame.draw.rect(s, fill, (x, y, int(w * min(ratio, 1.0)), h), border_radius=4)


def draw_hud(s, game, fonts):
    hero = game["hero"]
    need = rules.xp_needed(SPEC, game["level"])
    # top left: HP bar, XP bar, level
    draw_bar(s, 10, 10, 150, 14, hero["hp"] / hero["max_hp"], HP_BACK, HP_BAR)
    draw_bar(s, 10, 28, 150, 10, game["xp"] / need, XP_BACK, XP_BAR)
    draw_text(s, fonts["small"], f"Lv {game['level']}   HP {hero['hp']:.0f}", (10, 42))
    draw_text(s, fonts["small"], f"Kills {game['kills']}", (10, 58))
    # top right: the timer
    draw_text(s, fonts["small"],
              f"{fmt_time(game['time'])} / {fmt_time(SPEC['victory']['goal_time'])}",
              (s.get_width() - 10, 10), anchor="topright")
    # bottom: what you have
    draw_text(s, fonts["small"], inventory_text(game),
              (12, s.get_height() - 8), anchor="bottomleft")


def wrap_text(font, text, max_width):
    """Break one line of text into lines that fit the card."""
    lines = []
    line = ""
    for word in text.split():
        trial = (line + " " + word).strip()
        if font.size(trial)[0] > max_width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines


def card_rects(size):
    """The three card boxes. Drawing and clicking use the same numbers."""
    w, h = size
    cw, ch, gap = 330, 150, 18
    top = (h - (3 * ch + 2 * gap)) // 2 + 40
    x = (w - cw) // 2
    return [pygame.Rect(x, top + i * (ch + gap), cw, ch) for i in range(3)]


def card_at(rects, pos):
    for index, rect in enumerate(rects):
        if rect.collidepoint(pos):
            return index
    return None


def draw_card(s, rect, card, fonts):
    item = SPEC["items"][card["kind"]]
    pygame.draw.rect(s, CARD_BACK, rect, border_radius=12)
    pygame.draw.rect(s, CARD_EDGE, rect, width=3, border_radius=12)
    inner = rect.inflate(-36, 0)
    draw_text(s, fonts["mid"], item["name"], (inner.x, rect.y + 16))
    if item["kind"] != "special":
        draw_text(s, fonts["small"], f"Level {card['level']}", (inner.x, rect.y + 52),
                  colour=(170, 210, 250))
    for i, line in enumerate(wrap_text(fonts["small"], item["text"], inner.width)):
        draw_text(s, fonts["small"], line, (inner.x, rect.y + 80 + i * 20),
                  colour=(220, 220, 220))


def draw_level_up(s, game, fonts):
    overlay = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    overlay.fill((*OVERLAY, 210))
    s.blit(overlay, (0, 0))
    draw_text(s, fonts["big"], f"LEVEL {game['level'] + 1}!",
              (s.get_width() // 2, 70), colour=CARD_NAME, anchor="center")
    draw_text(s, fonts["small"], "Click or tap a card",
              (s.get_width() // 2, 115), colour=(180, 180, 180), anchor="center")
    rects = card_rects(s.get_size())
    for rect, card in zip(rects, game["cards"]):
        draw_card(s, rect, card, fonts)


def draw_end(s, game, fonts):
    """VICTORY or GAME OVER, with the time, the kills and the level."""
    won = game["state"] == "won"
    overlay = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    overlay.fill((*OVERLAY, 230))
    s.blit(overlay, (0, 0))
    draw_text(s, fonts["big"], "VICTORY" if won else "GAME OVER",
              (s.get_width() // 2, 240),
              colour=(120, 235, 140) if won else (240, 100, 100), anchor="midtop")
    draw_text(s, fonts["mid"], f"Survived {fmt_time(game['time'])}",
              (s.get_width() // 2, 300), anchor="center")
    draw_text(s, fonts["mid"], f"Kills {game['kills']}",
              (s.get_width() // 2, 332), anchor="center")
    draw_text(s, fonts["mid"], f"Level {game['level']}",
              (s.get_width() // 2, 364), anchor="center")
    draw_text(s, fonts["small"], "Click or tap to play again",
              (s.get_width() // 2, 420), colour=(180, 180, 180), anchor="center")


def draw_paused(s, fonts):
    overlay = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    overlay.fill((*OVERLAY, 140))
    s.blit(overlay, (0, 0))
    draw_text(s, fonts["big"], "PAUSED",
              (s.get_width() // 2, s.get_height() // 2), anchor="center")


async def main():
    pygame.init()
    pygame.display.set_mode((SPEC["window"]["width"], SPEC["window"]["height"]))
    pygame.display.set_caption("Night Survivors")
    load_images()
    if pygame.mixer.get_init() is None:
        print("No sound device: the game runs without sound.")
    else:
        pygame.mixer.set_num_channels(8)
        load_sounds()
    clock = pygame.time.Clock()
    fonts = {
        "small": load_font(22),
        "mid": load_font(30),
        "big": load_font(52),
    }

    game = rules.new_game(SPEC)
    touch = None
    paused = False

    while True:
        surface = pygame.display.get_surface()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_p:
                paused = not paused
            if event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION):
                touch = (event.x * surface.get_width(),
                         event.y * surface.get_height())
            if event.type == pygame.FINGERUP:
                touch = None

            tap = None
            if event.type == pygame.MOUSEBUTTONDOWN:
                tap = event.pos
            elif event.type == pygame.FINGERDOWN:
                tap = touch
            elif event.type == pygame.KEYDOWN and game["state"] in ENDED:
                tap = (0, 0)  # on the end screen any key also starts a new game
            if tap is not None:
                if game["state"] in ENDED:
                    game = rules.new_game(SPEC)
                    paused = False
                elif game["state"] == "levelup":
                    index = card_at(card_rects(surface.get_size()), tap)
                    if index is not None:
                        game = rules.choose_card(game, index)

        if game["state"] == "playing":
            if touch is not None:
                # Phone: walk toward the finger while it touches the screen.
                target = screen_to_world(game, *touch)
            else:
                mouse = pygame.mouse.get_pos()
                wx, wy = screen_to_world(game, *mouse)
                # Computer: keep walking while the pointer is farther than the dead zone.
                dx = wx - game["hero"]["x"]
                dy = wy - game["hero"]["y"]
                if math.hypot(dx, dy) > SPEC["hero"]["mouse_dead_zone"]:
                    target = (wx, wy)
                else:
                    target = None
        else:
            # The game is paused for the cards or it is over: nobody walks.
            target = None
        game["target"] = target

        if not paused:
            game = rules.step(game, STEP)

        # What just happened? Each event has its own short sound.
        for name in game["events"]:
            play(name)
        game["events"].clear()

        s = surface
        draw_floor(s, game)
        for enemy in game["enemies"]:
            draw_enemy(s, game, enemy)
        draw_effects(s, game)
        draw_flashes(s, game)
        draw_numbers(s, game, fonts["small"])
        draw_hud(s, game, fonts)
        if game["state"] in ENDED:
            draw_end(s, game, fonts)
        elif game["state"] == "levelup":
            draw_level_up(s, game, fonts)
        elif paused:
            draw_paused(s, fonts)
        pygame.display.flip()

        clock.tick(60)
        await asyncio.sleep(0)


if __name__ == "__main__":
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    asyncio.run(main())
