"""Draws the mod icon options (512 x 512) from scratch, plus a side-by-side compare sheet.

python -I previews/icon_mockup.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
S = 512
GREEN = (124, 176, 32)
DARK = (22, 24, 22)
PANEL = (34, 37, 33)
WHITE = (235, 235, 230)
DIM = (150, 150, 145)
ORANGE = (255, 150, 40)
RED = (230, 90, 70)
LIGHTGREEN = (140, 200, 60)


def font(size, bold=True):
    return ImageFont.truetype("C:/Windows/Fonts/" + ("segoeuib.ttf" if bold else "segoeui.ttf"), size)


def background():
    img = Image.new("RGB", (S, S), DARK)
    d = ImageDraw.Draw(img)
    # soft vertical gradient
    for y in range(S):
        t = y / S
        c = tuple(int(a + (b - a) * t) for a, b in zip((44, 50, 38), (18, 20, 18)))
        d.line((0, y, S, y), fill=c)
    return img


def shadow(img, box, radius=18, offset=10):
    sh = Image.new("L", (S, S), 0)
    ImageDraw.Draw(sh).rounded_rectangle((box[0] + offset, box[1] + offset, box[2] + offset, box[3] + offset), radius, fill=170)
    sh = sh.filter(ImageFilter.GaussianBlur(14))
    black = Image.new("RGB", (S, S), (0, 0, 0))
    img.paste(black, (0, 0), sh)


def sheet(img, box, rows):
    """A ledger page: green header, striped rows with orange/green amounts."""
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box
    shadow(img, box)
    d.rounded_rectangle(box, 18, fill=PANEL)
    d.rounded_rectangle((x0, y0, x1, y0 + 70), 18, fill=GREEN)
    d.rectangle((x0, y0 + 40, x1, y0 + 70), fill=GREEN)
    y = y0 + 90
    for i, (bar, value, color) in enumerate(rows):
        if i % 2 == 1:
            d.rectangle((x0 + 10, y - 6, x1 - 10, y + 30), fill=(42, 46, 40))
        d.rounded_rectangle((x0 + 24, y + 6, x0 + 24 + bar, y + 18), 6, fill=DIM)
        d.text((x1 - 24, y + 12), value, font=font(30), fill=color, anchor="rm")
        y += 42
    return d


def option_a():
    """Ledger sheet + calendar tab: 'monthly' and 'sheet' in one look."""
    img = background()
    rows = [(150, "-206K", ORANGE), (110, "-14K", ORANGE), (130, "-11K", ORANGE), (90, "-7K", ORANGE), (120, "+42K", LIGHTGREEN)]
    d = sheet(img, (60, 110, 452, 470), rows)
    # month tab on top
    shadow(img, (150, 40, 362, 150), 16, 6)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((150, 40, 362, 150), 16, fill=WHITE)
    d.rectangle((150, 40, 362, 78), fill=RED)
    d.rounded_rectangle((150, 40, 362, 90), 16, fill=RED)
    d.rectangle((150, 72, 362, 90), fill=RED)
    d.text((256, 64), "MONTH", font=font(30), fill=WHITE, anchor="mm")
    d.text((256, 122), "OCT", font=font(46), fill=DARK, anchor="mm")
    for rx in (195, 317):
        d.rounded_rectangle((rx - 7, 26, rx + 7, 56), 6, fill=DIM)
    return img


def option_b():
    """Big dollar sign falling out of a ledger: 'where is my money going'."""
    img = background()
    rows = [(150, "-206K", ORANGE), (110, "-14K", ORANGE), (130, "-11K", ORANGE), (90, "-7K", ORANGE), (120, "-3K", ORANGE), (100, "+42K", LIGHTGREEN)]
    sheet(img, (40, 60, 360, 470), rows)
    d = ImageDraw.Draw(img)
    # dollar coin with a down arrow
    shadow(img, (300, 250, 490, 440), 95, 8)
    d = ImageDraw.Draw(img)
    d.ellipse((300, 250, 490, 440), fill=(230, 180, 40), outline=(160, 120, 20), width=8)
    d.text((395, 343), "$", font=font(130), fill=(120, 85, 10), anchor="mm")
    d.polygon([(440, 160), (500, 160), (470, 215)], fill=RED)
    d.rectangle((458, 110, 482, 165), fill=RED)
    return img


def option_c():
    """Clean text badge: big minus amount over a mini bar chart."""
    img = background()
    d = ImageDraw.Draw(img)
    shadow(img, (40, 40, 472, 472), 30)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((40, 40, 472, 472), 30, fill=PANEL)
    d.rounded_rectangle((40, 40, 472, 130), 30, fill=GREEN)
    d.rectangle((40, 95, 472, 130), fill=GREEN)
    d.text((256, 86), "EXPENSES", font=font(54), fill=DARK, anchor="mm")
    heights = [120, 180, 90, 260, 150, 210]
    for i, h in enumerate(heights):
        x = 80 + i * 62
        color = ORANGE if i != 3 else RED
        d.rounded_rectangle((x, 430 - h, x + 44, 430), 8, fill=color)
    d.line((70, 432, 442, 432), fill=DIM, width=4)
    return img


options = {"A": option_a(), "B": option_b(), "C": option_c()}
for name, img in options.items():
    img.save(HERE / f"icon_option{name}_v1.png")

sheet_img = Image.new("RGB", (3 * 400 + 80, 470), (30, 32, 30))
d = ImageDraw.Draw(sheet_img)
for i, (name, img) in enumerate(options.items()):
    x = 20 + i * 420
    sheet_img.paste(img.resize((400, 400), Image.LANCZOS), (x, 20))
    d.text((x + 200, 445), f"Option {name}", font=font(28), fill=WHITE, anchor="mm")
sheet_img.save(HERE / "icon_options_v1.png")
print("saved")


# --- Option B with the Pro Edition banner at the very top (user's pick, 2026-10-31) ---------------------
def option_b_pro():
    import importlib.util
    banner_py = HERE.parents[1] / "Library" / "_ProEditionBanner" / "add_banner.py"
    spec = importlib.util.spec_from_file_location("add_banner", banner_py)
    add_banner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(add_banner)

    # option B shrunk to fit under the 71 px banner
    img = background()
    art = option_b().crop((20, 40, 512, 490)).resize((440, 403), Image.LANCZOS)
    img.paste(art, (36, 92))
    banner = add_banner.make_banner(1.0)
    img.paste(banner, ((S - banner.width) // 2, 8), banner)
    return img


option_b_pro().save(HERE / "icon_optionB_pro_v1.png")
print("saved pro")
