"""Generate Chinese README visual assets using Pillow.

Creates 6 PNG files in assets/:
- hero-zh-light.png / hero-zh-dark.png
- before-after-zh-light.png / before-after-zh-dark.png
- owm-architecture-zh-light.png / owm-architecture-zh-dark.png
"""

from PIL import Image, ImageDraw, ImageFont
import os
import math

ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)


def get_font(size, bold=False):
    """Use Microsoft JhengHei (Traditional Chinese font)."""
    try:
        if bold:
            return ImageFont.truetype("msjhbd.ttc", size)
        return ImageFont.truetype("msjh.ttc", size)
    except Exception:
        try:
            if bold:
                return ImageFont.truetype("msyhbd.ttc", size)
            return ImageFont.truetype("msyh.ttc", size)
        except Exception:
            return ImageFont.load_default()


def get_en_font(size, bold=False):
    """English font for mixed content."""
    try:
        if bold:
            return ImageFont.truetype("arialbd.ttf", size)
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return get_font(size, bold)


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
    if fill:
        draw.rectangle([x0+r, y0, x1-r, y1], fill=fill)
        draw.rectangle([x0, y0+r, x1, y1-r], fill=fill)
        draw.pieslice([x0, y0, x0+2*r, y0+2*r], 180, 270, fill=fill)
        draw.pieslice([x1-2*r, y0, x1, y0+2*r], 270, 360, fill=fill)
        draw.pieslice([x0, y1-2*r, x0+2*r, y1], 90, 180, fill=fill)
        draw.pieslice([x1-2*r, y1-2*r, x1, y1], 0, 90, fill=fill)
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

    # Gradient background
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
    for i in range(0, W, 60):
        for j in range(0, H, 60):
            if (i + j) % 120 == 0:
                draw.ellipse([i-2, j-2, i+2, j+2], fill=accent_rgb)

    # Main title (keep English for brand name)
    title_font = get_en_font(56, bold=True)
    title = "TradeMemory Protocol"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 90), title, fill=hex_to_rgb(t["text"]), font=title_font)

    # Chinese tagline
    tag_font = get_font(26)
    tagline = "AI 交易代理的記憶層"
    bbox = draw.textbbox((0, 0), tagline, font=tag_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 170), tagline, fill=hex_to_rgb(t["text2"]), font=tag_font)

    # Stats line in Chinese
    stats_font = get_font(18)
    stats = "v0.5.1  |  1,233 測試  |  17 MCP 工具  |  5 記憶類型  |  進化引擎"
    bbox = draw.textbbox((0, 0), stats, font=stats_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 230), stats, fill=hex_to_rgb(t["accent"]), font=stats_font)

    # Bottom accent line
    line_y = 300
    line_w = 400
    draw.line([(W//2 - line_w//2, line_y), (W//2 + line_w//2, line_y)],
              fill=hex_to_rgb(t["accent"]), width=3)

    # Branding
    brand_font = get_font(14)
    brand = "Mnemox AI 專案"
    bbox = draw.textbbox((0, 0), brand, font=brand_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 340), brand, fill=hex_to_rgb(t["text2"]), font=brand_font)

    path = os.path.join(ASSETS_DIR, f"hero-zh-{theme_name}.png")
    img.save(path, "PNG", optimize=True)
    print(f"  Created {path}")


def generate_before_after(theme_name):
    t = THEMES[theme_name]
    W, H = 1440, 520
    img = Image.new("RGB", (W, H), hex_to_rgb(t["bg"]))
    draw = ImageDraw.Draw(img)

    # Title
    title_font = get_font(28, bold=True)
    title = "使用前 vs 使用後"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 20), title, fill=hex_to_rgb(t["text"]), font=title_font)

    card_w = 620
    card_h = 340
    left_x = 60
    card_y = 70

    # Left card (Without Memory)
    draw_rounded_rect(draw, (left_x, card_y, left_x + card_w, card_y + card_h),
                      16, fill=hex_to_rgb(t["card_bg"]),
                      outline=hex_to_rgb(t["red"]), width=2)

    header_font = get_font(22, bold=True)
    draw.text((left_x + 30, card_y + 20), "沒有記憶",
              fill=hex_to_rgb(t["red"]), font=header_font)

    # Left flow
    flow_font = get_font(15, bold=True)
    flow_y = card_y + 80
    steps_left = ["交易", "遺忘", "交易", "遺忘", "重蹈覆轍"]
    step_colors = [t["text2"], t["red"], t["text2"], t["red"], t["red"]]

    x_pos = left_x + 40
    for i, (step, color) in enumerate(zip(steps_left, step_colors)):
        bbox = draw.textbbox((0, 0), step, font=flow_font)
        sw = bbox[2] - bbox[0]
        sh = bbox[3] - bbox[1]

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

    # Left descriptions
    desc_font = get_font(15)
    descriptions_left = [
        "每次對話都從零開始",
        "不記得過去的錯誤",
        "重複相同的虧損模式",
        "無法適應市場變化",
    ]
    for i, desc in enumerate(descriptions_left):
        y = card_y + 150 + i * 28
        draw.text((left_x + 40, y), "X", fill=hex_to_rgb(t["red"]), font=get_font(15, bold=True))
        draw.text((left_x + 65, y), desc, fill=hex_to_rgb(t["text2"]), font=desc_font)

    # Right card (With TradeMemory)
    right_x = W - 60 - card_w

    draw_rounded_rect(draw, (right_x, card_y, right_x + card_w, card_y + card_h),
                      16, fill=hex_to_rgb(t["card_bg"]),
                      outline=hex_to_rgb(t["green"]), width=2)

    draw.text((right_x + 30, card_y + 20), "有 TradeMemory",
              fill=hex_to_rgb(t["green"]), font=header_font)

    # Right flow
    steps_right = ["交易", "記住", "學習", "適應", "進化"]
    step_colors_r = [t["text2"], t["accent"], t["accent2"], t["cyan"], t["green"]]

    x_pos = right_x + 50
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

    # Right descriptions
    descriptions_right = [
        "每筆交易都帶完整上下文記錄",
        "自動發現交易模式",
        "市場狀態改變時自動適應",
        "自主進化新策略",
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

    draw.text((100, bar_y + 12), "手動交易日誌：", fill=hex_to_rgb(t["text2"]), font=compare_font)
    draw.text((310, bar_y + 12), "每天 2 小時", fill=hex_to_rgb(t["red"]), font=compare_bold)

    draw_arrow(draw, (W//2 - 30, bar_y + bar_h//2), (W//2 + 30, bar_y + bar_h//2),
               hex_to_rgb(t["accent"]), 3)

    draw.text((W//2 + 60, bar_y + 12), "TradeMemory：", fill=hex_to_rgb(t["text2"]), font=compare_font)
    draw.text((W//2 + 260, bar_y + 12), "0 秒", fill=hex_to_rgb(t["green"]), font=compare_bold)

    path = os.path.join(ASSETS_DIR, f"before-after-zh-{theme_name}.png")
    img.save(path, "PNG", optimize=True)
    print(f"  Created {path}")


def generate_architecture(theme_name):
    t = THEMES[theme_name]
    W, H = 1440, 600
    img = Image.new("RGB", (W, H), hex_to_rgb(t["bg"]))
    draw = ImageDraw.Draw(img)

    # Title
    title_font = get_font(28, bold=True)
    title = "結果加權記憶 (OWM) 架構"
    bbox = draw.textbbox((0, 0), title, font=title_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, 20), title, fill=hex_to_rgb(t["text"]), font=title_font)

    # Five memory type cards
    memory_types = [
        ("情節記憶", "發生了什麼？", "交易事件\n+ 上下文", t["accent"]),
        ("語義記憶", "我相信什麼？", "貝氏\n信念", t["accent2"]),
        ("程序記憶", "我怎麼做？", "行為\n模式", t["cyan"]),
        ("情感記憶", "我感覺如何？", "信心\n+ 回撤", t["orange"]),
        ("前瞻記憶", "下一步？", "條件式\n計畫", t["green"]),
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

        draw_rounded_rect(draw, (x, card_y, x + card_w, card_y + card_h),
                          12, fill=hex_to_rgb(t["card_bg"]),
                          outline=hex_to_rgb(color), width=3)

        # Color accent bar
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

    draw_rounded_rect(draw, (engine_x, engine_y, engine_x + engine_w, engine_y + engine_h),
                      16, fill=hex_to_rgb(t["accent"]),
                      outline=hex_to_rgb(t["accent2"]), width=3)

    engine_font = get_font(22, bold=True)
    engine_text = "結果加權回憶引擎"
    bbox = draw.textbbox((0, 0), engine_text, font=engine_font)
    ew = bbox[2] - bbox[0]
    draw.text((engine_x + (engine_w - ew) // 2, engine_y + 12), engine_text,
              fill=hex_to_rgb("#FFFFFF"), font=engine_font)

    sub_font = get_en_font(14)
    sub_text = "Score(m, C) = Q x Sim x Rec x Conf x Aff"
    bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    sw = bbox[2] - bbox[0]
    draw.text((engine_x + (engine_w - sw) // 2, engine_y + 46), sub_text,
              fill=hex_to_rgb("#E0E7FF"), font=sub_font)

    # Connection lines
    engine_center_y = engine_y
    for i, (cx, cy) in enumerate(card_centers):
        color = memory_types[i][3]
        mid_y = cy + (engine_center_y - cy) // 2
        draw.line([(cx, cy), (cx, mid_y)], fill=hex_to_rgb(color), width=2)
        draw.line([(cx, mid_y), (W // 2, mid_y)], fill=hex_to_rgb(color), width=2)
        draw.line([(W // 2, mid_y), (W // 2, engine_center_y)], fill=hex_to_rgb(color), width=2)

    # Bottom: data sources
    source_y = engine_y + engine_h + 40
    source_font = get_font(16)
    sources_text = "MT5  |  Binance  |  REST API  |  MCP Protocol  |  手動輸入"
    bbox = draw.textbbox((0, 0), sources_text, font=source_font)
    sw = bbox[2] - bbox[0]
    draw.text(((W - sw) // 2, source_y), sources_text,
              fill=hex_to_rgb(t["text2"]), font=source_font)

    draw_arrow(draw, (W // 2, source_y - 5), (W // 2, engine_y + engine_h + 5),
               hex_to_rgb(t["text2"]), 2)

    path = os.path.join(ASSETS_DIR, f"owm-architecture-zh-{theme_name}.png")
    img.save(path, "PNG", optimize=True)
    print(f"  Created {path}")


if __name__ == "__main__":
    print("Generating Chinese README assets...")
    for theme in ["light", "dark"]:
        print(f"\n--- {theme.upper()} theme ---")
        generate_hero(theme)
        generate_before_after(theme)
        generate_architecture(theme)
    print("\nDone! All Chinese assets in", ASSETS_DIR)
