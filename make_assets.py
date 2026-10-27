"""Make the picture files in assets/. Run this on your computer:

    python make_assets.py

It reads the small 16x16 pictures in raw_art/ (Kenney, CC0) and writes them
into assets/ three times bigger. The upscale uses whole pixels only, so the
art stays crisp (no blurring). It also makes two bright crystal gems by
colouring raw_art/gem.png: blue for XP 1 and pink for XP 2.

raw_art/ is never changed. main.py only reads the finished files.
"""

import os

from PIL import Image

SCALE = 3
HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_art")
OUT = os.path.join(HERE, "assets")

# every raw picture that the game draws, copied 3x bigger
COPY = [
    "hero.png",
    "bat.png",
    "slime.png",
    "ghost.png",
    "demon.png",
    "floor.png",
    "sword.png",
]

# the gem shape coloured into a bright crystal: dark -> light, 4 shades
GEMS = {
    "gem_blue.png": [
        (26, 62, 158),
        (58, 122, 232),
        (126, 196, 255),
        (238, 248, 255),
    ],
    "gem_pink.png": [
        (146, 28, 104),
        (232, 62, 158),
        (255, 138, 206),
        (255, 240, 250),
    ],
}


def upscale(image):
    """Make every pixel of the picture SCALE x SCALE pixels. No smoothing."""
    return image.resize((image.width * SCALE, image.height * SCALE), Image.NEAREST)


def colour_gem(base, shades):
    """Paint the gem shape with a 4 shade ramp, keeping its outline and alpha.

    A dark pixel gets the dark shade and a light pixel the light shade, so the
    original shading of the picture survives the recolouring.
    """
    result = Image.new("RGBA", base.size, (0, 0, 0, 0))
    src = base.convert("RGBA")
    pixels = src.load()
    out = result.load()
    for y in range(base.height):
        for x in range(base.width):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            lightness = (r + g + b) / 3
            shade = min(int(lightness / 64), 3)
            out[x, y] = (*shades[shade], a)
    return result


def main():
    os.makedirs(OUT, exist_ok=True)
    made = []
    for name in COPY:
        upscale(Image.open(os.path.join(RAW, name)).convert("RGBA")).save(
            os.path.join(OUT, name))
        made.append(name)

    gem = Image.open(os.path.join(RAW, "gem.png")).convert("RGBA")
    for name, shades in GEMS.items():
        upscale(colour_gem(gem, shades)).save(os.path.join(OUT, name))
        made.append(name)

    size = 16 * SCALE
    print(f"wrote {len(made)} files to assets/ (each {size} x {size} pixels):")
    for name in made:
        print("  ", name)


if __name__ == "__main__":
    main()
