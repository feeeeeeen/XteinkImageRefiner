"""
XteinkImageRefiner アイコン生成スクリプト
Pillow で 256x256 のアイコンを描画し、マルチサイズ .ico として保存する。
"""

from PIL import Image, ImageDraw, ImageFont
import math


def draw_rounded_rect(draw, xy, radius, fill=None, outline=None, width=1):
    """角丸四角形を描画する"""
    x0, y0, x1, y1 = xy
    r = radius
    # 四隅の円弧
    draw.pieslice([x0, y0, x0 + 2*r, y0 + 2*r], 180, 270, fill=fill, outline=outline, width=width)
    draw.pieslice([x1 - 2*r, y0, x1, y0 + 2*r], 270, 360, fill=fill, outline=outline, width=width)
    draw.pieslice([x0, y1 - 2*r, x0 + 2*r, y1], 90, 180, fill=fill, outline=outline, width=width)
    draw.pieslice([x1 - 2*r, y1 - 2*r, x1, y1], 0, 90, fill=fill, outline=outline, width=width)
    # 中央部を塗りつぶし
    draw.rectangle([x0 + r, y0, x1 - r, y1], fill=fill)
    draw.rectangle([x0, y0 + r, x1, y1 - r], fill=fill)


def draw_image_frame(draw, x, y, w, h, border_color, bg_color, shadow_color=None):
    """画像フレーム（写真のようなモチーフ）を描画する"""
    if shadow_color:
        draw.rectangle([x + 3, y + 3, x + w + 3, y + h + 3], fill=shadow_color)
    draw.rectangle([x, y, x + w, y + h], fill=border_color)
    margin = max(3, int(w * 0.06))
    draw.rectangle([x + margin, y + margin, x + w - margin, y + h - margin], fill=bg_color)


def draw_mountain_scene(draw, x, y, w, h):
    """画像フレーム内に山と太陽のシンプルなシーンを描画"""
    inner_x = x
    inner_y = y
    inner_w = w
    inner_h = h

    # 太陽（右上の円）
    sun_r = int(inner_w * 0.1)
    sun_cx = inner_x + int(inner_w * 0.72)
    sun_cy = inner_y + int(inner_h * 0.28)
    draw.ellipse([sun_cx - sun_r, sun_cy - sun_r, sun_cx + sun_r, sun_cy + sun_r],
                 fill=(255, 210, 80))

    # 山（三角形）
    # 大きい山
    m1_peak = (inner_x + int(inner_w * 0.38), inner_y + int(inner_h * 0.30))
    m1_left = (inner_x, inner_y + inner_h)
    m1_right = (inner_x + int(inner_w * 0.76), inner_y + inner_h)
    draw.polygon([m1_peak, m1_left, m1_right], fill=(100, 160, 130))

    # 小さい山
    m2_peak = (inner_x + int(inner_w * 0.68), inner_y + int(inner_h * 0.45))
    m2_left = (inner_x + int(inner_w * 0.40), inner_y + inner_h)
    m2_right = (inner_x + inner_w, inner_y + inner_h)
    draw.polygon([m2_peak, m2_left, m2_right], fill=(70, 130, 110))


def draw_resize_arrows(draw, cx, cy, size, color, thickness=3):
    """対角線上のリサイズ矢印（↗↙）を描画"""
    half = size // 2
    arrow_len = int(size * 0.28)

    # 対角線
    draw.line([(cx - half, cy + half), (cx + half, cy - half)], fill=color, width=thickness)

    # 右上の矢じり
    tx, ty = cx + half, cy - half
    draw.line([(tx, ty), (tx - arrow_len, ty)], fill=color, width=thickness)
    draw.line([(tx, ty), (tx, ty + arrow_len)], fill=color, width=thickness)

    # 左下の矢じり
    bx, by = cx - half, cy + half
    draw.line([(bx, by), (bx + arrow_len, by)], fill=color, width=thickness)
    draw.line([(bx, by), (bx, by - arrow_len)], fill=color, width=thickness)


def draw_stack_indicator(draw, x, y, w, h, color):
    """複数画像の重なりを示すスタック線"""
    offset = 5
    draw.line([(x + offset, y - offset), (x + w + offset, y - offset)], fill=color, width=2)
    draw.line([(x + w + offset, y - offset), (x + w + offset, y + h - offset)], fill=color, width=2)

    draw.line([(x + 2*offset, y - 2*offset), (x + w + 2*offset, y - 2*offset)], fill=color, width=2)
    draw.line([(x + w + 2*offset, y - 2*offset), (x + w + 2*offset, y + h - 2*offset)], fill=color, width=2)


def generate_icon(size=256):
    """メインのアイコン画像を生成"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # --- 背景: 角丸四角形（ダークティール～ブルーのグラデーション風） ---
    bg_margin = int(size * 0.04)
    bg_radius = int(size * 0.18)

    # グラデーション風の背景を作成（上部が暗い青、下部がティール）
    bg = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    bg_draw = ImageDraw.Draw(bg)

    for i in range(size):
        t = i / size
        r = int(20 + t * 15)
        g = int(30 + t * 50)
        b = int(60 + t * 30)
        bg_draw.line([(bg_margin, i), (size - bg_margin, i)], fill=(r, g, b, 255))

    # 角丸マスク
    mask = Image.new('L', (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    draw_rounded_rect(mask_draw, [bg_margin, bg_margin, size - bg_margin, size - bg_margin],
                      bg_radius, fill=255)
    bg.putalpha(mask)
    img = Image.alpha_composite(img, bg)
    draw = ImageDraw.Draw(img)

    # --- メインモチーフ: 重なった画像フレーム ---
    frame_w = int(size * 0.52)
    frame_h = int(size * 0.42)
    frame_x = int(size * 0.14)
    frame_y = int(size * 0.22)

    # 背面のフレーム（少し傾斜した位置に配置で重なりを表現）
    back_offset = int(size * 0.04)
    draw_image_frame(draw, frame_x + back_offset * 2, frame_y - back_offset,
                     frame_w, frame_h,
                     border_color=(180, 200, 210, 180),
                     bg_color=(60, 80, 100, 150),
                     shadow_color=None)

    draw_image_frame(draw, frame_x + back_offset, frame_y - back_offset // 2,
                     frame_w, frame_h,
                     border_color=(200, 215, 225, 200),
                     bg_color=(50, 70, 90, 180),
                     shadow_color=None)

    # 前面のメインフレーム
    draw_image_frame(draw, frame_x, frame_y,
                     frame_w, frame_h,
                     border_color=(230, 240, 245),
                     bg_color=(45, 65, 95),
                     shadow_color=(10, 15, 25, 100))

    # フレーム内に山と太陽のシーン
    inner_margin = max(3, int(frame_w * 0.06))
    draw_mountain_scene(draw,
                        frame_x + inner_margin, frame_y + inner_margin,
                        frame_w - 2 * inner_margin, frame_h - 2 * inner_margin)

    # --- リサイズ矢印（右下） ---
    arrow_cx = int(size * 0.74)
    arrow_cy = int(size * 0.74)
    arrow_size = int(size * 0.22)

    # 矢印の背景円
    arrow_bg_r = int(size * 0.15)
    draw.ellipse([arrow_cx - arrow_bg_r, arrow_cy - arrow_bg_r,
                  arrow_cx + arrow_bg_r, arrow_cy + arrow_bg_r],
                 fill=(40, 120, 180, 230))
    draw.ellipse([arrow_cx - arrow_bg_r + 2, arrow_cy - arrow_bg_r + 2,
                  arrow_cx + arrow_bg_r - 2, arrow_cy + arrow_bg_r - 2],
                 fill=(30, 100, 160, 230))

    draw_resize_arrows(draw, arrow_cx, arrow_cy, arrow_size,
                       color=(240, 250, 255), thickness=max(2, int(size * 0.014)))

    return img


def main():
    # 256x256 で描画
    icon_256 = generate_icon(256)

    # PNG として保存（確認用）
    icon_256.save('icon.png', 'PNG')
    print('icon.png saved (256x256)')

    # マルチサイズ ICO として保存
    # Pillow の ICO プラグインは、元画像から指定サイズへリサイズして格納する
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon_256.save(
        'icon.ico',
        format='ICO',
        sizes=sizes,
    )
    print(f'icon.ico saved (sizes: {[s[0] for s in sizes]})')


if __name__ == '__main__':
    main()
