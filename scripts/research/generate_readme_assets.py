"""Generate README visual assets using Pillow.

Creates 6 PNG files in assets/:
- hero-light.png / hero-dark.png
- before-after-light.png / before-after-dark.png
- owm-architecture-light.png / owm-architecture-dark.png
"""

from PIL import Image, ImageDraw, ImageFont
import os

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)

# Fonts
def get_font(size, bold=False):
    try:
        if bold:
            return ImageFont.truetype("arialbd.ttf", size)
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()

# Colors
THEMES = {
    "light": {
        "bg": "#FFFFFF",
        "bg2": "#F8FAFC",
        "text": "#1E293B",
        "text2": "#64748B",
        "accent": "#3B82F6",
        "accent2": "#8B5CF6",
        "green": "#10B981",
        "red": "#EF4444",
        "orange": "#F59E0B",
        "pink": "#EC4899",
        "cyan": "#06B6D4",
        "card_bg": "#F1F5F9",
        "card_border": "#E2E8F0",
        "gradient_start": "#EFF6FF",
        "gradient_end": "#F5F3FF",
    },
    "dark": {
        "bg": "#0F172A",
        "bg2": "#1E293B",
        "text": "#F1F5F9",
        "text2": "#94A3B8",
        "accent": "#60A5FA",
        "accent2": "#A78BFA",
        "green": "#34D399",
        "red": "#F87171",
        "orange": "#FBBF24",
        "pink": "#F472B6",
        "cyan": "#22D3EE",
        "card_bg": "#1E293B",
        "card_border": "#334155",
        "gradient_start": "#1E293B",
        "gradient_end": "#1E1B4B",
    },
}


def hex_to_rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))


def draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    x0, y0, x1, y1 = xy
    r = radius
    # Fill
    if fill:
        draw.rectangle([x0+r, y0, x1-r, y1], fill=fill)
        draw.rectangle([x0, y0+r, x1, y1-r], fill=fill)
        draw.pieslice([x0, y0, x0+2*r, y0+2*r], 180, 270, fill=fill)
        draw.pieslice([x1-2*r, y0, x1, y0+2*r], 270, 360, fill=fill)
        draw.pieslice([x0, y1-2*r, x0+2*r, y1], 90, 180, fill=fill)
        draw.pieslice([x1-2*r, y1-2*r, x1, y1], 0, 90, fill=fill)
    # Outline
    if outline:
        draw.arc([x0, y0, x0+2*r, y0+2*r], 180, 270, fill=outline, width=width)
        draw.arc([x1-2*r, y0, x1, y0+2*r], 270, 360, fill=outline, width=width)
        draw.arc([x0, y1-2*r, x0+2*r, y1], 90, 180, fill=outline, width=width)
        draw.arc([x1-2*r, y1-2*r, x1, y1], 0, 90, fill=outline, width=width)
        draw.line([x0+r, y0, x1-r, y0], fill=outline, width=width)
        draw.line([x0+r, y1, x1-r, y1], fill=outline, width=width)
        draw.line([x0, y0+r, x0, y1-r], fill=outline, width=width)
        draw.line([x1, y0+r, x1, y1-r], fill=outline, width=width)


def draw_arrow(draw, start, end, color, width=3):
    draw.line([start, end], fill=color, width=width)
    # Arrowhead
    import math
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    angle = math.atan2(dy, dx)
    arrow_len = 12
    arrow_angle = math.pi / 6
    x1 = end[0] - arrow_len * math.cos(angle - arrow_angle)
    y1 = end[1] - arrow_len * math.sin(angle - arrow_angle)
    x2 = end[0] - arrow_len * math.cos(angle + arrow_angle)
    y2 = end[1] - arrow_len * math.sin(angle + arrow_angle)
    draw.polygon([end, (x1, y1), (x2, y2)], fill=color)


def generate_hero(theme_name):
    t = THEMES[theme_name]
    W, H = 1440, 400
    img = Image.new("RGB", (W, H), hex_to_rgb(t["bg"]))
    draw = ImageDraw.Draw(img)

    # Gradient background band
    for y in range(H):
        ratio = y / H
        r1, g1, b1 = hex_to_rgb(t["gradient_start"])
        r2, g2, b2 = hex_to_rgb(t["gradient_end"])
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Decorative dots
    accent_rgb = hex_to_rgb(t["accent"])
    accent2_rgb = hex_to_rgb(t["accent2"])
    for i in range(0, W, 60):
        for j in range(0, H, 60):
            alpha_r = max(0, min(255, accent_rgb[0] + (30 if (i+j) % 120 == 0 else 0)))
            if (i + j) % 120 == 0:
                draw.ellipse([i-2, j-2, i+2, j+2], fill=(*accent_rgb[:2], min(255, accent_rgb[2])))

    # Main title
    title_font = get_font(56, bold=True)
    title = "TradeMemory Protocol"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 100), title, fill=hex_to_rgb(t["text"]), font=title_font)

    # Tagline
    tag_font = get_font(24)
    tagline = "The Memory Layer for AI Trading Agents"
    bbox = draw.textbbox((0, 0), tagline, font=tag_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 175), tagline, fill=hex_to_rgb(t["text2"]), font=tag_font)

    # Version + stats line
    stats_font = get_font(18)
    stats = "v0.5.1  |  1,233 Tests  |  17 MCP Tools  |  5 Memory Types  |  Evolution Engine"
    bbox = draw.textbbox((0, 0), stats, font=stats_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 230), stats, fill=hex_to_rgb(t["accent"]), font=stats_font)

    # Bottom accent line
    line_y = 300
    line_w = 400
    draw.line([(W//2 - line_w//2, line_y), (W//2 + line_w//2, line_y)],
              fill=hex_to_rgb(t["accent"]), width=3)

    # Mnemox branding
    brand_font = get_font(14)
    brand = "A Mnemox AI Project"
    bbox = draw.textbbox((0, 0), brand, font=brand_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 340), brand, fill=hex_to_rgb(t["text2"]), font=brand_font)

    path = os.path.join(ASSETS_DIR, f"hero-{theme_name}.png")
    img.save(path, "PNG", optimize=True)
    print(f"  Created {path}")


def generate_before_after(theme_name):
    t = THEMES[theme_name]
    W, H = 1440, 520
    img = Image.new("RGB", (W, H), hex_to_rgb(t["bg"]))
    draw = ImageDraw.Draw(img)

    # Title
    title_font = get_font(28, bold=True)
    title = "Before vs After"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 20), title, fill=hex_to_rgb(t["text"]), font=title_font)

    # Left card (Without Memory) - red tones
    card_w = 620
    card_h = 340
    left_x = 60
    card_y = 70

    # Left card background
    draw_rounded_rect(draw, (left_x, card_y, left_x + card_w, card_y + card_h),
                      16, fill=hex_to_rgb(t["card_bg"]),
                      outline=hex_to_rgb(t["red"]), width=2)

    # Left header
    header_font = get_font(22, bold=True)
    draw.text((left_x + 30, card_y + 20), "Without Memory",
              fill=hex_to_rgb(t["red"]), font=header_font)

    # Left flow: Trade → Forget → Trade → Forget → Same Mistakes
    flow_font = get_font(16, bold=True)
    flow_y = card_y + 80
    steps_left = ["Trade", "Forget", "Trade", "Forget", "Same Mistakes"]
    step_colors = [t["text2"], t["red"], t["text2"], t["red"], t["red"]]

    x_pos = left_x + 40
    for i, (step, color) in enumerate(zip(steps_left, step_colors)):
        bbox = draw.textbbox((0, 0), step, font=flow_font)
        sw = bbox[2] - bbox[0]
        sh = bbox[3] - bbox[1]

        # Step box
        box_w = sw + 24
        box_h = sh + 16
        draw_rounded_rect(draw, (x_pos, flow_y, x_pos + box_w, flow_y + box_h),
                          8, fill=hex_to_rgb(color if i in [1, 3, 4] else t["card_bg"]),
                          outline=hex_to_rgb(color), width=2)

        text_color = t["bg"] if i in [1, 3, 4] else color
        draw.text((x_pos + 12, flow_y + 8), step,
                  fill=hex_to_rgb(text_color), font=flow_font)

        if i < len(steps_left) - 1:
            arrow_start = (x_pos + box_w + 5, flow_y + box_h // 2)
            arrow_end = (x_pos + box_w + 25, flow_y + box_h // 2)
            draw_arrow(draw, arrow_start, arrow_end, hex_to_rgb(t["text2"]), 2)
            x_pos += box_w + 30
        else:
            x_pos += box_w

    # Left description lines
    desc_font = get_font(15)
    descriptions_left = [
        "Every session starts from zero",
        "No memory of past mistakes",
        "Repeats the same losing patterns",
        "No adaptation to market changes",
    ]
    for i, desc in enumerate(descriptions_left):
        y = card_y + 150 + i * 28
        # Red X
        draw.text((left_x + 40, y), "X", fill=hex_to_rgb(t["red"]), font=get_font(15, bold=True))
        draw.text((left_x + 65, y), desc, fill=hex_to_rgb(t["text2"]), font=desc_font)

    # Right card (With TradeMemory) - green tones
    right_x = W - 60 - card_w

    draw_rounded_rect(draw, (right_x, card_y, right_x + card_w, card_y + card_h),
                      16, fill=hex_to_rgb(t["card_bg"]),
                      outline=hex_to_rgb(t["green"]), width=2)

    draw.text((right_x + 30, card_y + 20), "With TradeMemory",
              fill=hex_to_rgb(t["green"]), font=header_font)

    # Right flow: Trade → Remember → Learn → Adapt → Evolve
    steps_right = ["Trade", "Remember", "Learn", "Adapt", "Evolve"]
    step_colors_r = [t["text2"], t["accent"], t["accent2"], t["cyan"], t["green"]]

    x_pos = right_x + 30
    flow_y = card_y + 80
    for i, (step, color) in enumerate(zip(steps_right, step_colors_r)):
        bbox = draw.textbbox((0, 0), step, font=flow_font)
        sw = bbox[2] - bbox[0]
        sh = bbox[3] - bbox[1]

        box_w = sw + 24
        box_h = sh + 16
        draw_rounded_rect(draw, (x_pos, flow_y, x_pos + box_w, flow_y + box_h),
                          8, fill=hex_to_rgb(color),
                          outline=hex_to_rgb(color), width=2)

        draw.text((x_pos + 12, flow_y + 8), step,
                  fill=hex_to_rgb(t["bg"] if theme_name == "dark" else "#FFFFFF"), font=flow_font)

        if i < len(steps_right) - 1:
            arrow_start = (x_pos + box_w + 5, flow_y + box_h // 2)
            arrow_end = (x_pos + box_w + 25, flow_y + box_h // 2)
            draw_arrow(draw, arrow_start, arrow_end, hex_to_rgb(color), 2)
            x_pos += box_w + 30
        else:
            x_pos += box_w

    # Right description lines
    descriptions_right = [
        "Every trade recorded with full context",
        "Patterns discovered automatically",
        "Adapts when market regime changes",
        "Evolves new strategies autonomously",
    ]
    for i, desc in enumerate(descriptions_right):
        y = card_y + 150 + i * 28
        draw.text((right_x + 40, y), "+", fill=hex_to_rgb(t["green"]), font=get_font(15, bold=True))
        draw.text((right_x + 65, y), desc, fill=hex_to_rgb(t["text2"]), font=desc_font)

    # Bottom comparison bar
    bar_y = card_y + card_h + 30
    bar_h = 50
    draw_rounded_rect(draw, (60, bar_y, W - 60, bar_y + bar_h),
                      12, fill=hex_to_rgb(t["card_bg"]),
                      outline=hex_to_rgb(t["card_border"]), width=1)

    compare_font = get_font(18)
    compare_bold = get_font(18, bold=True)

    # Left side of bar
    draw.text((100, bar_y + 14), "Manual trade journaling:", fill=hex_to_rgb(t["text2"]), font=compare_font)
    draw.text((370, bar_y + 14), "2 hrs/day", fill=hex_to_rgb(t["red"]), font=compare_bold)

    # Arrow in middle
    draw_arrow(draw, (W//2 - 30, bar_y + bar_h//2), (W//2 + 30, bar_y + bar_h//2),
               hex_to_rgb(t["accent"]), 3)

    # Right side of bar
    draw.text((W//2 + 60, bar_y + 14), "TradeMemory:", fill=hex_to_rgb(t["text2"]), font=compare_font)
    draw.text((W//2 + 230, bar_y + 14), "0 seconds", fill=hex_to_rgb(t["green"]), font=compare_bold)

    path = os.path.join(ASSETS_DIR, f"before-after-{theme_name}.png")
    img.save(path, "PNG", optimize=True)
    print(f"  Created {path}")


def generate_architecture(theme_name):
    t = THEMES[theme_name]
    W, H = 1440, 600
    img = Image.new("RGB", (W, H), hex_to_rgb(t["bg"]))
    draw = ImageDraw.Draw(img)

    # Title
    title_font = get_font(28, bold=True)
    title = "Outcome-Weighted Memory (OWM)"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 20), title, fill=hex_to_rgb(t["text"]), font=title_font)

    # Five memory type cards
    memory_types = [
        ("Episodic", "What happened?", "Trade events\n+ context", t["accent"]),
        ("Semantic", "What do I believe?", "Bayesian\nbeliefs", t["accent2"]),
        ("Procedural", "How do I act?", "Behavioral\npatterns", t["cyan"]),
        ("Affective", "How do I feel?", "Confidence\n+ drawdown", t["orange"]),
        ("Prospective", "What's next?", "Conditional\nplans", t["green"]),
    ]

    card_w = 220
    card_h = 160
    gap = 30
    total_w = 5 * card_w + 4 * gap
    start_x = (W - total_w) // 2
    card_y = 80

    name_font = get_font(20, bold=True)
    question_font = get_font(14)
    desc_font = get_font(13)

    card_centers = []

    for i, (name, question, desc, color) in enumerate(memory_types):
        x = start_x + i * (card_w + gap)

        # Card
        draw_rounded_rect(draw, (x, card_y, x + card_w, card_y + card_h),
                          12, fill=hex_to_rgb(t["card_bg"]),
                          outline=hex_to_rgb(color), width=3)

        # Color accent bar at top
        draw_rounded_rect(draw, (x, card_y, x + card_w, card_y + 6),
                          3, fill=hex_to_rgb(color))

        # Name
        bbox = draw.textbbox((0, 0), name, font=name_font)
        nw = bbox[2] - bbox[0]
        draw.text((x + (card_w - nw) // 2, card_y + 20), name,
                  fill=hex_to_rgb(color), font=name_font)

        # Question
        bbox = draw.textbbox((0, 0), question, font=question_font)
        qw = bbox[2] - bbox[0]
        draw.text((x + (card_w - qw) // 2, card_y + 55), question,
                  fill=hex_to_rgb(t["text2"]), font=question_font)

        # Description
        lines = desc.split("\n")
        for j, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=desc_font)
            lw = bbox[2] - bbox[0]
            draw.text((x + (card_w - lw) // 2, card_y + 90 + j * 20), line,
                      fill=hex_to_rgb(t["text"]), font=desc_font)

        card_centers.append((x + card_w // 2, card_y + card_h))

    # Central Recall Engine box
    engine_w = 500
    engine_h = 80
    engine_x = (W - engine_w) // 2
    engine_y = card_y + card_h + 80

    # Gradient-like fill for engine box
    draw_rounded_rect(draw, (engine_x, engine_y, engine_x + engine_w, engine_y + engine_h),
                      16, fill=hex_to_rgb(t["accent"]),
                      outline=hex_to_rgb(t["accent2"]), width=3)

    engine_font = get_font(22, bold=True)
    engine_text = "Outcome-Weighted Recall Engine"
    bbox = draw.textbbox((0, 0), engine_text, font=engine_font)
    ew = bbox[2] - bbox[0]
    draw.text((engine_x + (engine_w - ew) // 2, engine_y + 12), engine_text,
              fill=hex_to_rgb("#FFFFFF"), font=engine_font)

    sub_font = get_font(14)
    sub_text = "Score(m, C) = Q x Sim x Rec x Conf x Aff"
    bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = bbox[2] - bbox[0]
    draw.text((engine_x + (engine_w - sw) // 2, engine_y + 46), sub_text,
              fill=hex_to_rgb("#E0E7FF"), font=sub_font)

    # Connection lines from cards to engine
    engine_center_y = engine_y
    for i, (cx, cy) in enumerate(card_centers):
        color = memory_types[i][3]
        # Draw line from card bottom to engine top
        mid_y = cy + (engine_center_y - cy) // 2
        draw.line([(cx, cy), (cx, mid_y)], fill=hex_to_rgb(color), width=2)
        draw.line([(cx, mid_y), (W // 2, mid_y)], fill=hex_to_rgb(color), width=2)
        draw.line([(W // 2, mid_y), (W // 2, engine_center_y)], fill=hex_to_rgb(color), width=2)

    # Bottom: data sources
    source_y = engine_y + engine_h + 40
    source_font = get_font(16)
    sources_text = "MT5  |  Binance  |  REST API  |  MCP Protocol  |  Manual Input"
    bbox = draw.textbbox((0, 0), sources_text, font=source_font)
    sw = bbox[2] - bbox[0]
    draw.text(((W - sw) // 2, source_y), sources_text,
              fill=hex_to_rgb(t["text2"]), font=source_font)

    # Arrow up from sources to engine
    draw_arrow(draw, (W // 2, source_y - 5), (W // 2, engine_y + engine_h + 5),
               hex_to_rgb(t["text2"]), 2)

    path = os.path.join(ASSETS_DIR, f"owm-architecture-{theme_name}.png")
    img.save(path, "PNG", optimize=True)
    print(f"  Created {path}")


if __name__ == "__main__":
    print("Generating README assets...")
    for theme in ["light", "dark"]:
        print(f"\n--- {theme.upper()} theme ---")
        generate_hero(theme)
        generate_before_after(theme)
        generate_architecture(theme)
    print("\nDone! All assets in", ASSETS_DIR)
