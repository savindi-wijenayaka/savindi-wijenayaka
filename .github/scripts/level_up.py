#!/usr/bin/env python3
"""
Updates career.json and regenerates XP category bars in both header SVGs.

Modes:
  new-year   — level+1, category+1 (default: industry)
  correction — level unchanged, swap industry -> correct category

Bar rendering logic:
  ALL three bars (academia, industry, rest) always render `total` squares —
  one per level year. When total increases, every bar gains an extra empty
  square and the square size shrinks proportionally to stay within the fixed
  bar width. Only the filled count differs per category (how many years were
  spent there). This means a level-up visually extends all three bars equally,
  while only the relevant category gets one more filled square.

Overflow handling:
  Bar width is fixed at 116px. Square size is calculated to fit `total`
  squares with decreasing gaps as level grows:
    level  7 → 14px squares, 3px gap
    level 10 →  8px squares, 3px gap   (minimum square size)
    level 12 →  8px squares, 1px gap
    level 14+→  thin proportional bar  (fallback mode)
"""

import json
import re
import argparse
import math
from pathlib import Path

REPO_ROOT    = Path(__file__).parent.parent.parent
CAREER_JSON  = REPO_ROOT / '.github' / 'career.json'
HEADER_LIGHT = REPO_ROOT / 'assets' / 'header.svg'
HEADER_DARK  = REPO_ROOT / 'assets' / 'header-dark.svg'

# Fixed bar geometry
BAR_CENTERS  = {'academia': 175, 'industry': 450, 'rest': 725}
BAR_WIDTH    = 116   # px — width each bar occupies
LABEL_Y      = 188
SQUARES_Y    = 196
MIN_SQUARE   = 8     # px — below this, switch to thin-bar mode
THIN_BAR_H   = 8     # px — height of thin bar fallback

COLORS = {
    'light': {
        'academia': ('#8b6914', '.85', '#2d1b00', '.12'),
        'industry': ('#065f46', '.75', '#2d1b00', '.12'),
        'rest':     ('#8b6914', '.35', '#2d1b00', '.12'),
    },
    'dark': {
        'academia': ('#c9a227', '.9',  '#c9a227', '.12'),
        'industry': ('#a78bfa', '.85', '#a78bfa', '.12'),
        'rest':     ('#c9a227', '.3',  '#c9a227', '.12'),
    },
}

LABEL_COLORS = {
    'light': {'academia': '#8b6914', 'industry': '#065f46', 'rest': ('#8b6914', ' opacity=".5"')},
    'dark':  {'academia': '#c9a227', 'industry': '#a78bfa', 'rest': ('#c9a227', ' opacity=".5"')},
}

CATEGORY_LABELS = {
    'academia': '(left)',
    'industry': '(middle \u2014 accent)',
    'rest':     '(right)',
}


def calc_square_params(total):
    """Return (size, gap) fitting `total` squares in BAR_WIDTH px, or None for thin-bar mode."""
    for gap in [3, 2, 1]:
        size = (BAR_WIDTH - (total - 1) * gap) / total
        if size >= MIN_SQUARE:
            return math.floor(size), gap
    return None, None  # thin-bar mode


def label_attrs(category, theme):
    entry = LABEL_COLORS[theme][category]
    if isinstance(entry, tuple):
        color, extra = entry
    else:
        color, extra = entry, ''
    return color, extra


def render_square_bar(category, filled, total, size, gap, theme):
    fill_col, fill_op, empty_col, empty_op = COLORS[theme][category]
    cx = BAR_CENTERS[category]
    total_width = total * size + (total - 1) * gap
    start_x = cx - total_width // 2

    lines = []
    for i in range(total):
        x = start_x + i * (size + gap)
        if i < filled:
            lines.append(
                f'  <rect x="{x}" y="{SQUARES_Y}" width="{size}" height="{size}" rx="1" fill="{fill_col}" opacity="{fill_op}"/>'
            )
        else:
            lines.append(
                f'  <rect x="{x}" y="{SQUARES_Y}" width="{size}" height="{size}" rx="1" fill="{empty_col}" opacity="{empty_op}"/>'
            )
    return '\n'.join(lines)


def render_thin_bar(category, filled, total, theme):
    """Fallback: proportional filled bar when squares get too small."""
    fill_col, fill_op, empty_col, empty_op = COLORS[theme][category]
    cx = BAR_CENTERS[category]
    start_x = cx - BAR_WIDTH // 2
    filled_w = round(BAR_WIDTH * filled / total)

    lines = [
        f'  <rect x="{start_x}" y="{SQUARES_Y}" width="{BAR_WIDTH}" height="{THIN_BAR_H}" rx="3" fill="{empty_col}" opacity="{empty_op}"/>',
        f'  <rect x="{start_x}" y="{SQUARES_Y}" width="{filled_w}" height="{THIN_BAR_H}" rx="3" fill="{fill_col}" opacity="{fill_op}"/>',
    ]
    return '\n'.join(lines)


def generate_bars_section(career, theme):
    total = career['total']
    size, gap = calc_square_params(total)
    use_thin = size is None

    lines = ['  <!-- XP category bars -->']
    for cat in ['academia', 'industry', 'rest']:
        label = CATEGORY_LABELS[cat]
        color, opacity_attr = label_attrs(cat, theme)
        cx = BAR_CENTERS[cat]
        lines.append(f'  <!-- {cat.upper()} {label} -->')
        lines.append(
            f'  <text x="{cx}" y="{LABEL_Y}" text-anchor="middle" '
            f'font-family="\'Courier New\', Courier, monospace" font-size="10" '
            f'letter-spacing="1" fill="{color}"{opacity_attr}>{cat.upper()}</text>'
        )
        if use_thin:
            lines.append(render_thin_bar(cat, career[cat], total, theme))
        else:
            lines.append(render_square_bar(cat, career[cat], total, size, gap, theme))
        lines.append('')

    return '\n'.join(lines).rstrip()


def update_svg(path, career, theme):
    content = path.read_text()

    # Update LVL number in badge
    content = re.sub(r'LVL \d+', f'LVL {career["total"]}', content)

    # Replace category bars section (between markers)
    new_bars = generate_bars_section(career, theme)
    content = re.sub(
        r'  <!-- XP category bars -->.*?(?=\n  <!-- XP bar -->)',
        new_bars + '\n',
        content,
        flags=re.DOTALL,
    )

    path.write_text(content)
    print(f'Updated {path.name}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--category', default='industry', choices=['industry', 'academia', 'rest'])
    parser.add_argument('--mode', default='new-year', choices=['new-year', 'correction'])
    args = parser.parse_args()

    career = json.loads(CAREER_JSON.read_text())

    if args.mode == 'new-year':
        career['total'] += 1
        career[args.category] += 1
    elif args.mode == 'correction':
        # Undo the auto-applied industry increment, apply correct category
        if career['industry'] <= 0:
            raise ValueError('industry count is already 0, cannot correct further')
        career['industry'] -= 1
        career[args.category] += 1

    CAREER_JSON.write_text(json.dumps(career, indent=2) + '\n')
    print(f"career.json → total={career['total']} industry={career['industry']} academia={career['academia']} rest={career['rest']}")

    update_svg(HEADER_LIGHT, career, 'light')
    update_svg(HEADER_DARK,  career, 'dark')


if __name__ == '__main__':
    main()
