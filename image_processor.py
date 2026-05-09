from __future__ import annotations

import os
import zipfile
import uuid
import tempfile
import struct
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import cv2
import numpy as np
from datetime import datetime, timezone
from xml.sax.saxutils import escape
from PIL import Image, ImageFilter, ImageEnhance

# 量子化LUT: point() にリストを渡すとPillowのC実装でLUT適用されるため
# lambdaより大幅に高速。モジュールロード時に一度だけ生成する。
# 1-bit: 0-127 → 0 (黒), 128-255 → 255 (白)
_LUT_1BIT: list[int] = [0] * 128 + [255] * 128
# 2-bit (4階調): 各値を最近傍パレット値 [0, 85, 170, 255] にマッピング
# 閾値: 0-42→0, 43-127→85, 128-212→170, 213-255→255
_LUT_2BIT: list[int] = [0] * 43 + [85] * 85 + [170] * 85 + [255] * 43

# Numba JIT: インストール済みの場合に Atkinson ループを C 速度でコンパイルする。
# nogil=True により ThreadPoolExecutor と組み合わせた真の並列実行が可能。
# 未インストール時はフォールバック (list ベース) を使用するため動作は変わらない。
_NUMBA_AVAILABLE = False
try:
    import numba as _numba

    @_numba.njit(cache=True, nogil=True)
    def _atkinson_1bit_jit(buf: np.ndarray, height: int, width: int, PAD: int) -> None:
        for y in range(height):
            for x in range(width):
                px = x + PAD
                old_val = buf[y, px]
                new_val = 255.0 if old_val >= 127.5 else 0.0
                buf[y, px] = new_val
                err = (old_val - new_val) / 8.0
                buf[y,     px + 1] += err
                buf[y,     px + 2] += err
                buf[y + 1, px - 1] += err
                buf[y + 1, px    ] += err
                buf[y + 1, px + 1] += err
                buf[y + 2, px    ] += err

    @_numba.njit(cache=True, nogil=True)
    def _atkinson_2bit_jit(buf: np.ndarray, height: int, width: int, PAD: int) -> None:
        for y in range(height):
            for x in range(width):
                px = x + PAD
                old_val = buf[y, px]
                if   old_val < 42.5:  new_val = 0.0
                elif old_val < 127.5: new_val = 85.0
                elif old_val < 212.5: new_val = 170.0
                else:                 new_val = 255.0
                buf[y, px] = new_val
                err = (old_val - new_val) / 8.0
                buf[y,     px + 1] += err
                buf[y,     px + 2] += err
                buf[y + 1, px - 1] += err
                buf[y + 1, px    ] += err
                buf[y + 1, px + 1] += err
                buf[y + 2, px    ] += err

    _NUMBA_AVAILABLE = True
except Exception:
    pass

def split_image_top_bottom(img: Image.Image) -> tuple[Image.Image, Image.Image]:
    """
    画像を上下2分割して (top, bottom) のタプルで返す。
    奇数ピクセル高さの場合、上側を1px多くする。
    """
    w, h = img.size
    mid = h // 2
    top = img.crop((0, 0, w, mid + (h % 2)))
    bottom = img.crop((0, mid + (h % 2), w, h))
    return top, bottom

def split_image_left_right(img: Image.Image) -> tuple[Image.Image, Image.Image]:
    """
    画像を左右2分割して (left, right) のタプルで返す。
    奇数ピクセル幅の場合、左側を1px多くする。
    """
    w, h = img.size
    mid = w // 2
    left = img.crop((0, 0, mid + (w % 2), h))
    right = img.crop((mid + (w % 2), 0, w, h))
    return left, right

def rotate_image_90cw(img: Image.Image) -> Image.Image:
    """
    画像を時計回りに90度回転して返す。
    800x600 → 600x800 になる。
    """
    return img.rotate(-90, expand=True)

def should_auto_rotate(img_w: int, img_h: int, target_w: int, target_h: int) -> bool:
    """
    画像を90度回転した方がターゲット領域をより大きく使えるか判定する。
    回転なし: min(target_w/img_w, target_h/img_h)
    回転あり: min(target_w/img_h, target_h/img_w)
    回転した方が比率が大きければTrueを返す。
    """
    ratio_normal = min(target_w / img_w, target_h / img_h)
    ratio_rotated = min(target_w / img_h, target_h / img_w)
    return ratio_rotated > ratio_normal

def detect_trim_rect(img: Image.Image, threshold: int = 240, margin: int = 2) -> tuple[int, int, int, int]:
    """
    画像の余白を自動検出し、コンテンツ領域の (left, top, right, bottom) を返す。
    PIL Image.crop() に直接渡せる形式。

    アルゴリズム:
    1. グレースケール変換 → numpy配列化
    2. threshold 未満のピクセルを「コンテンツ」とするバイナリマスク作成
    3. 行/列の非白ピクセル数が全幅/全高の1%未満のラインはスパースノイズ
       （ページ番号等）として除外
    4. コンテンツ行/列の最初と最後でクロップ範囲を決定
    5. margin ピクセルの安全マージンを外側に追加（画像境界でクランプ）
    6. コンテンツ未検出時は画像全体 (0, 0, w, h) を返す
    """
    w, h = img.size
    gray = img.convert("L")
    arr = np.array(gray, dtype=np.uint8)

    # バイナリマスク: threshold未満 = コンテンツ
    mask = arr < threshold

    # 行ごと・列ごとの非白ピクセル数
    row_counts = mask.sum(axis=1)  # shape: (h,)
    col_counts = mask.sum(axis=0)  # shape: (w,)

    # スパースコンテンツ除去閾値
    row_threshold = max(1, int(w * 0.01))
    col_threshold = max(1, int(h * 0.01))

    significant_rows = np.where(row_counts >= row_threshold)[0]
    significant_cols = np.where(col_counts >= col_threshold)[0]

    if len(significant_rows) == 0 or len(significant_cols) == 0:
        return (0, 0, w, h)

    top = int(significant_rows[0])
    bottom = int(significant_rows[-1]) + 1
    left = int(significant_cols[0])
    right = int(significant_cols[-1]) + 1

    # 安全マージン追加
    left = max(0, left - margin)
    top = max(0, top - margin)
    right = min(w, right + margin)
    bottom = min(h, bottom + margin)

    return (left, top, right, bottom)

def detect_trim_rect_fast(img: Image.Image, threshold: int = 240, margin: int = 2, max_dim: int = 800) -> tuple[int, int, int, int]:
    """
    サムネイルで余白検出し、元の座標系にスケールバックする高速版。
    バックグラウンド一括検出用。
    """
    w, h = img.size
    if max(w, h) <= max_dim:
        return detect_trim_rect(img, threshold, margin)

    scale = max_dim / max(w, h)
    thumb_w, thumb_h = int(w * scale), int(h * scale)
    thumb = img.resize((thumb_w, thumb_h), Image.Resampling.NEAREST)

    tl, tt, tr, tb = detect_trim_rect(thumb, threshold, margin=0)

    # スケールバック
    left = max(0, int(tl / scale) - margin)
    top = max(0, int(tt / scale) - margin)
    right = min(w, int(tr / scale) + margin)
    bottom = min(h, int(tb / scale) + margin)

    return (left, top, right, bottom)

def apply_processing(img: Image.Image, max_width: int, max_height: int, use_grayscale: bool = False, bits: int = 8, alignment: str = "center", blur_strength: int = 0, contrast: int = 0, crop_rect: tuple[int, int, int, int] | None = None, auto_rotate: bool = False, sharpen: int = 0, clahe: int = 0, no_resize: bool = False) -> Image.Image:
    """
    PIL Imageオブジェクトに指定の設定を適用して返す（プレビュー用）。
    no_resize=True の場合、リサイズ・自動回転・シャープ・白背景合成をスキップし、入力画像のサイズをそのまま維持する。
    """
    # クロップ（リサイズ前に適用）
    if crop_rect is not None:
        img = img.crop(crop_rect)

    # 自動回転（クロップ後・リサイズ前）— リサイズなし時はスキップ（ターゲットサイズがないため）
    if not no_resize and auto_rotate and should_auto_rotate(img.width, img.height, max_width, max_height):
        img = rotate_image_90cw(img)

    # 元のサイズを取得
    original_width, original_height = img.size

    # プレぼかし（リサイズ前に適用し、細い文字のかすれを防止）
    if blur_strength > 0:
        radius = blur_strength / 100 * 3.0  # 0-100 → 0.0-3.0
        img = img.filter(ImageFilter.GaussianBlur(radius=radius))

    if no_resize:
        # リサイズなし: リサイズ・シャープ・白背景合成をスキップ
        pass
    else:
        # 縦横比を維持したリサイズ計算
        ratio = min(max_width / original_width, max_height / original_height)
        new_width = max(1, int(original_width * ratio))
        new_height = max(1, int(original_height * ratio))

        # cv2.INTER_AREA でリサイズ（ダウンスケール時に最も高品質）
        arr = np.array(img)
        arr = cv2.resize(arr, (new_width, new_height), interpolation=cv2.INTER_AREA)
        img = Image.fromarray(arr)

        # アンシャープマスク（リサイズ後のエッジ復元）
        if sharpen > 0:
            radius = 1.5
            percent = int(sharpen * 1.5)  # 0-100 → 0-150%
            img = img.filter(ImageFilter.UnsharpMask(radius=radius, percent=percent, threshold=2))

    # グレースケール化処理
    if use_grayscale:
        img = img.convert("L")
        # CLAHE（局所コントラスト最適化。グレースケール後・コントラスト前に適用）
        if clahe > 0:
            clip_limit = max(0.5, clahe / 100 * 4.0)  # 0-100 → 0.5-4.0
            clahe_obj = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
            img = Image.fromarray(clahe_obj.apply(np.array(img)))
        # コントラスト調整（グレースケール後・量子化前。パディング前に適用し白背景の影響を回避）
        if contrast > 0:
            factor = 1.0 + contrast / 100  # 0→1.0(無変更), 100→2.0
            img = ImageEnhance.Contrast(img).enhance(factor)
        if bits < 8:
            levels = 2 ** bits
            factor = 255 / (levels - 1)
            lut = [int(round(p / factor) * factor) for p in range(256)]
            img = img.point(lut)

    if no_resize:
        # リサイズなし: 白背景合成をスキップし、画像をそのまま返す
        return img

    # 余白を白で埋める
    final_img = Image.new("L" if use_grayscale else "RGB", (max_width, max_height), 255 if use_grayscale else (255, 255, 255))

    if alignment == "top":
        left = (max_width - new_width) // 2
        top = 0
    else: # center
        left = (max_width - new_width) // 2
        top = (max_height - new_height) // 2

    final_img.paste(img, (left, top))

    return final_img

def resize_image(input_path: str, output_path: str, max_width: int, max_height: int, use_grayscale: bool = False, bits: int = 8, force_jpeg: bool = False, xtc_format: Optional[str] = None, alignment: str = "center", dither_algo: str = "None", dither_intensity: int = 0, clean_intensity: int = 0, clean_algo: str = "Median", img_override: Optional[Image.Image] = None, orig_ext: Optional[str] = None, blur_strength: int = 0, contrast: int = 0, crop_rect: tuple[int, int, int, int] | None = None, auto_rotate: bool = False, sharpen: int = 0, clahe: int = 0, no_resize: bool = False) -> Optional[str]:
    """
    画像をリサイズし、必要に応じてグレースケール化・フォーマット変換して保存する。
    img_override: PIL Image を直接渡す場合に使用（input_path は使われない）
    orig_ext: img_override 使用時の元拡張子 (例 ".jpg")。PNG 判定に利用。
    処理パイプライン:
    1. リサイズ & 白背景合成 (apply_processing)
    2. グレースケール化 & ディザリング (apply_bit_dithering)
    3. クリーンアップ & ビット削減 (save_xtg/xth または直接)
    """
    if img_override is not None:
        img = img_override.copy()
        ext_for_fmt = orig_ext or ".jpg"
    else:
        with Image.open(input_path) as _f:
            _f.load()
            img = _f.copy()
        ext_for_fmt = os.path.splitext(input_path)[1].lower()

    # 1. リサイズ & 背景合成
    img = apply_processing(img, max_width, max_height, use_grayscale, bits, alignment, blur_strength, contrast, crop_rect, auto_rotate, sharpen, clahe, no_resize=no_resize)
    
    # 2. グレースケール化 & ディザリング (強度調整込)
    # グレースケール無効かつ XTC 以外の場合はディザリングをスキップ（意図しないグレースケール化を防止）
    target_bits = 8
    if xtc_format == "XTG": target_bits = 1
    elif xtc_format == "XTH": target_bits = 2

    if use_grayscale or xtc_format:
        img = apply_bit_dithering(img, target_bits, dither_intensity, dither_algo)
        
    # 3. クリーンアップ & 保存
    if xtc_format:
        if xtc_format == "XTG":
            return save_xtg(img, output_path, clean_intensity, clean_algo)
        elif xtc_format == "XTH":
            return save_xth(img, output_path, clean_intensity, clean_algo)
    else:
        # XTC以外でもクリーンアップを適用可能にする
        if clean_intensity > 0:
            img = apply_cv2_cleaning(img, clean_intensity, clean_algo)

        # 保存フォーマットの決定
        if force_jpeg:
            save_format = "JPEG"
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
        else:
            save_format = "PNG" if ext_for_fmt == ".png" else "JPEG"
            if save_format == "JPEG" and img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            
        img.save(output_path, format=save_format, quality=95)
        return output_path

def apply_cv2_cleaning(img: Image.Image, intensity_pct: int, algo: str = "Median") -> Image.Image:
    """
    OpenCV を使用してノイズ除去を行う。
    algo: "Median", "Bilateral"
    intensity_pct: 0-100
    """
    if intensity_pct <= 0:
        return img
        
    # PIL -> OpenCV (numpy)。輝度チャンネルで処理し、最後に元モードへ戻す
    original_mode = img.mode
    img_l = img if img.mode == "L" else img.convert("L")

    cv_img = np.array(img_l)

    if algo == "Median":
        # 強度を100%出した場合でもボケすぎないよう、ksizeは最大5までに制限し、基本は3。
        # 代わりに、元画像とのブレンド率で強度を表現する。
        ksize = 3 if intensity_pct < 80 else 5
        res_cv = cv2.medianBlur(cv_img, ksize)
        res_pil = Image.fromarray(res_cv)
        # 強度をブレンド率(0.0-1.0)として適用
        alpha = intensity_pct / 100.0
        result = Image.blend(img_l, res_pil, alpha)
    elif algo == "Bilateral":
        # Bilateralもブレンドを導入して微調整を可能にする
        d = 9
        sigma = intensity_pct * 1.0
        res_cv = cv2.bilateralFilter(cv_img, d, sigma, sigma)
        res_pil = Image.fromarray(res_cv)
        alpha = intensity_pct / 100.0
        result = Image.blend(img_l, res_pil, alpha)
    else:
        return img

    # カラー画像を入力した場合は元のモードに戻す
    # 注: RGBA 入力では convert() によりアルファが 255 で上書きされるが、
    #     本アプリの入力画像は apply_processing 時点で白背景合成済みのため実害なし
    if original_mode != "L":
        result = result.convert(original_mode)
    return result

def apply_atkinson_dithering(img: Image.Image, target_bits: int = 1) -> Image.Image:
    """
    Atkinson法によるディザリングを適用する (Lモード画像用)。
    target_bits: 1 (2階調) または 2 (4階調)
    Numba が利用可能な場合は JIT コンパイル版 (C 速度・GIL 解放) を使用。
    フォールバック: Pythonリストアクセス + 閾値比較。
    誤差拡散の逐次依存性により完全なベクタライズは不可能。
    """
    img = img.convert("L")
    width, height = img.size

    # 右に2列・下に2行のパディングを追加して境界チェックを不要にする
    # (x-1, y+1) の最小 x は 0 なので左に1列のパディングも必要)
    PAD = 2
    buf = np.array(img, dtype=np.float32)
    buf_padded = np.pad(buf, ((0, PAD), (PAD, PAD)), constant_values=0.0)

    if _NUMBA_AVAILABLE:
        # JIT版: NumPy 配列をインプレース操作 (GIL 解放により並列実行可能)
        if target_bits == 1:
            _atkinson_1bit_jit(buf_padded, height, width, PAD)
        else:
            _atkinson_2bit_jit(buf_padded, height, width, PAD)
        result_arr = buf_padded
    else:
        # フォールバック: NumPy スカラーアクセス (~150ns/回) より Python リストアクセス
        # (~30ns/回) が高速。tolist() で一度だけ変換し、ループ内は純 Python で処理する。
        buf_list = buf_padded.tolist()
        if target_bits == 1:
            for y in range(height):
                row0 = buf_list[y]
                row1 = buf_list[y + 1]
                row2 = buf_list[y + 2]
                for x in range(width):
                    px = x + PAD
                    old_val = row0[px]
                    new_val = 255.0 if old_val >= 127.5 else 0.0
                    row0[px] = new_val
                    err = (old_val - new_val) / 8.0
                    # Atkinson拡散パターン（パディングにより境界チェック不要）
                    row0[px + 1] += err
                    row0[px + 2] += err
                    row1[px - 1] += err
                    row1[px    ] += err
                    row1[px + 1] += err
                    row2[px    ] += err
        else:
            for y in range(height):
                row0 = buf_list[y]
                row1 = buf_list[y + 1]
                row2 = buf_list[y + 2]
                for x in range(width):
                    px = x + PAD
                    old_val = row0[px]
                    if   old_val < 42.5:  new_val = 0.0
                    elif old_val < 127.5: new_val = 85.0
                    elif old_val < 212.5: new_val = 170.0
                    else:                 new_val = 255.0
                    row0[px] = new_val
                    err = (old_val - new_val) / 8.0
                    # Atkinson拡散パターン（パディングにより境界チェック不要）
                    row0[px + 1] += err
                    row0[px + 2] += err
                    row1[px - 1] += err
                    row1[px    ] += err
                    row1[px + 1] += err
                    row2[px    ] += err
        result_arr = np.array(buf_list, dtype=np.float32)

    result = np.clip(result_arr[:height, PAD:PAD + width], 0, 255).astype(np.uint8)
    return Image.fromarray(result, mode='L')

def apply_bit_dithering(img: Image.Image, target_bits: int, intensity_pct: int, algo: str = "None") -> Image.Image:
    """
    指定のビット数に対して、強度調整可能なディザリングを適用する。
    algo: "None", "Floyd-Steinberg", "Atkinson", "Sauvola"
    """
    img_l = img.convert("L")

    # 適応的二値化 (Sauvola): 局所的な閾値でテキストの可読性を最大化
    if algo == "Sauvola":
        arr = np.array(img_l)
        # ブロックサイズ: 画像短辺の1/8を基本とし、奇数に丸める (最小11, 最大101)
        short_side = min(arr.shape[:2])
        block_size = max(11, min(101, (short_side // 8) | 1))
        # 感度: intensity で調整 (0=グローバル量子化と同等, 100=最大適応)
        # C パラメータ: 高いほど暗い側に寄る。intensity が高いほどCを小さく (より適応的に)
        c_val = max(2, int(15 - intensity_pct * 0.13))  # 0→15, 100→2
        if target_bits == 1:
            result = cv2.adaptiveThreshold(
                arr, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)
            return Image.fromarray(result)
        elif target_bits == 2:
            # 多値適応: ローカル平均を基準に4階調にマッピング
            local_mean = cv2.GaussianBlur(arr.astype(np.float32), (block_size, block_size), 0)
            # ピクセル値とローカル平均の差で4レベルに分類
            diff = arr.astype(np.float32) - local_mean
            result = np.full_like(arr, 170)  # デフォルト: ライトグレー
            result[diff < -c_val * 2] = 0       # ローカル平均よりかなり暗い → 黒
            result[(diff >= -c_val * 2) & (diff < -c_val * 0.5)] = 85  # やや暗い → ダークグレー
            result[diff >= c_val * 0.5] = 255   # ローカル平均より明るい → 白
            return Image.fromarray(result)
        else:
            return img_l

    # 強度0、またはアルゴリズム「無し」の場合は単純量子化
    if intensity_pct <= 0 or algo == "None":
        if target_bits == 1:
            return img_l.point(_LUT_1BIT)
        elif target_bits == 2:
            return img_l.point(_LUT_2BIT)
        else:
            # target_bits=8 かつディザ無しの場合は元のモードを尊重
            return img if img.mode in ("RGB", "L") else img_l
        
    intensity = intensity_pct / 100.0
    
    if algo == "Floyd-Steinberg":
        # Floyd-Steinbergは事前ブレンドだと白飛びが激しいため、事後ブレンドに戻す
        if target_bits == 1:
            img_d = img_l.convert("1", dither=Image.Dither.FLOYDSTEINBERG).convert("L")
            img_q = img_l.point(_LUT_1BIT)
            return Image.blend(img_q, img_d, intensity)
        elif target_bits == 2 or target_bits == 8:
            # 2-bit または 8-bit 出力時。quantize ではなく convert("P") へのマッピングを再試行。
            # 白飛びを防ぐため、一度 L に戻してから変換する過程を精査。
            palette_data = [0,0,0, 85,85,85, 170,170,170, 255,255,255] + [255,255,255]*252
            p_img = Image.new("P", (1, 1))
            p_img.putpalette(palette_data)
            
            # quantize よりも convert("P") + palette 指定の方が階調が安定しやすいためこちらを使用。
            # ただし L モードからだと dither が効きにくいため、一時的に RGB 経由にする。
            img_rgb = img_l.convert("RGB")
            img_d = img_rgb.convert("P", palette=p_img, dither=Image.Dither.FLOYDSTEINBERG).convert("L")
            img_q = img_rgb.convert("P", palette=p_img, dither=Image.Dither.NONE).convert("L")
            return Image.blend(img_q, img_d, intensity)
        else:
            return img_l

    # Atkinsonは事前ブレンドの方が相性が良いため維持
    # 完全に量子化された画像(ポスタライズ)を作成
    if target_bits == 1:
        img_q = img_l.point(_LUT_1BIT)
    else:
        img_q = img_l.point(_LUT_2BIT)
    
    # 元画像と量子化画像をブレンド (強度分だけ元画像に近い入力を作る)
    img_mixed = Image.blend(img_q, img_l, intensity)
    
    if algo == "Atkinson":
        return apply_atkinson_dithering(img_mixed, target_bits)

    # 未知のアルゴリズム値: 量子化画像をそのまま返す (サイレントフォールバック)
    return img_q

def save_xtg(img: Image.Image, output_path: str, clean_intensity: int = 0, clean_algo: str = "Median") -> str:
    """
    PIL画像を 1-bit monochrome (XTG) 形式で保存する。
    """
    # 1. 2値化 (Lモードベース)
    img_l = img.convert("L")
    
    # 2. クリーンアップ (1bit化前に、OpenCVフィルターを適用)
    if clean_intensity > 0:
        img_l = apply_cv2_cleaning(img_l, clean_intensity, clean_algo)
        
    img_1bit = img_l.convert("1")
    
    w, h = img_1bit.size
    data = img_1bit.tobytes()
    
    data_size = len(data)
    md5_hash = hashlib.md5(data).digest()[:8]
    md5_val = struct.unpack("<Q", md5_hash)[0]
    
    header = struct.pack("<IHHBB IQ", 0x00475458, w, h, 0, 0, data_size, md5_val)
    
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(data)
    
    return output_path

def save_xth(img: Image.Image, output_path: str, clean_intensity: int = 0, clean_algo: str = "Median") -> str:
    """
    PIL画像を 2-bit grayscale (XTH) 形式で保存する。
    Xteinkの垂直スキャン・パッキング・LUTマッピング仕様。
    """
    img_l = img.convert("L")
    
    # 0. クリーンアップ (マッピング前に適用)
    if clean_intensity > 0:
        img_l = apply_cv2_cleaning(img_l, clean_intensity, clean_algo)
        
    w, h = img_l.size
    
    # 階調マッピング (NumPyベクトル化)
    # Xteink LUT Level: 0=White, 1=Dark Grey, 2=Light Grey, 3=Black
    arr = np.array(img_l, dtype=np.uint8)  # shape: (h, w)
    mapped = np.full_like(arr, 3, dtype=np.uint8)  # default: Black (<=63)
    mapped[arr > 191] = 0  # White
    mapped[(arr > 127) & (arr <= 191)] = 2  # Light Grey
    mapped[(arr > 63) & (arr <= 127)] = 1  # Dark Grey

    # XTHは Bit1 (MSB) と Bit2 (LSB) の2プレーン構成
    # pixelValue = (bit1 << 1) | bit2

    # 高さを8の倍数にパディング（不足分は0=White）
    pad_h = (8 - h % 8) % 8
    if pad_h:
        mapped = np.pad(mapped, ((0, pad_h), (0, 0)), constant_values=0)

    # 垂直スキャン (右から左、上から下、8ピクセル単位でビットパッキング)
    # 列を反転: 右→左
    mapped = mapped[:, ::-1]
    # (h_padded, w) → (w, groups, 8) に変形
    h_padded = mapped.shape[0]
    mapped = mapped.T.reshape(w, h_padded // 8, 8)

    bit1_arr = (mapped >> 1) & 1  # MSBプレーン
    bit2_arr = mapped & 1         # LSBプレーン

    # 8ビットを1バイトにパッキング (MSB = bit7 = topmost pixel)
    weights = np.array([128, 64, 32, 16, 8, 4, 2, 1], dtype=np.uint8)
    plane1 = (bit1_arr * weights).sum(axis=2).astype(np.uint8)
    plane2 = (bit2_arr * weights).sum(axis=2).astype(np.uint8)

    full_data = plane1.tobytes() + plane2.tobytes()
    
    data_size = len(full_data)
    # MD5はオプションだが、一応計算
    md5_hash = hashlib.md5(full_data).digest()[:8]
    md5_val = struct.unpack("<Q", md5_hash)[0]
    
    # Header (22 bytes) - Mark 0x00485458 ("XTH\0")
    header = struct.pack("<IHHBB IQ", 0x00485458, w, h, 0, 0, data_size, md5_val)
    
    with open(output_path, "wb") as f:
        f.write(header)
        f.write(full_data)
        
    return output_path

def create_xtc(image_paths: list[str], output_xtc_path: str, title: str, author: str, direction: int = 1, is_xtch: bool = False) -> str:
    """
    処理済みXTG/XTH画像リストからXTC/XTCHコンテナを生成する。
    direction: 0=LtoR, 1=RtoL, 2=TopToBottom
    """
    page_count = len(image_paths)
    mark = 0x48435458 if is_xtch else 0x00435458
    
    # Header offsets
    metadata_offset = 56
    chapter_offset = 0 # Currently no chapters
    index_offset = metadata_offset + 256
    data_offset = index_offset + (page_count * 16)
    
    # 1. Header (56 bytes)
    header = struct.pack("<I H H B B B B I Q Q Q Q Q",
                         mark,
                         0x0100, # version
                         page_count,
                         direction,
                         1,      # hasMetadata
                         0,      # hasThumbnails
                         0,      # hasChapters
                         1,      # currentPage (1-based)
                         metadata_offset,
                         index_offset,
                         data_offset,
                         0,      # thumbOffset
                         0       # chapterOffset
                         )
    
    # 2. Metadata (256 bytes)
    def encode_str(s, length):
        max_bytes = length - 1
        b = s.encode("utf-8")[:max_bytes]
        # マルチバイト文字の途中でカットされた場合に無効なUTF-8を除去する
        b = b.decode("utf-8", errors="ignore").encode("utf-8")
        return b.ljust(length, b'\0')
        
    metadata = encode_str(title, 128) + \
               encode_str(author, 64) + \
               encode_str("ImageOptimizer", 32) + \
               encode_str("ja", 16) + \
               struct.pack("<I", int(datetime.now().timestamp())) + \
               struct.pack("<H", 0) + \
               struct.pack("<H", 0) + \
               b'\0' * 8 # reserved
               
    # 3. Page Index Table (16 bytes per page)
    # We need to read each file to get size and dimensions
    page_entries = []
    current_offset = data_offset
    
    for img_path in image_paths:
        size = os.path.getsize(img_path)
        with open(img_path, "rb") as f:
            h_data = f.read(22)
            # Mark(4), Width(2), Height(2)
            _, w, h = struct.unpack("<IHH", h_data[:8])
        
        page_entries.append(struct.pack("<Q I H H", current_offset, size, w, h))
        current_offset += size
        
    index_table = b"".join(page_entries)
    
    # Write everything
    with open(output_xtc_path, "wb") as f:
        f.write(header)
        f.write(metadata)
        f.write(index_table)
        for img_path in image_paths:
            with open(img_path, "rb") as f_in:
                f.write(f_in.read())
                
    return output_xtc_path

def create_epub(image_paths: list[str], output_epub_path: str, title: str, author: str) -> None:
    """
    処理済み画像リストから固定レイアウト・右綴じのEPUB3を生成する。
    """
    book_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    
    with zipfile.ZipFile(output_epub_path, 'w', zipfile.ZIP_DEFLATED) as epub:
        # 1. mimetype (圧縮なし)
        epub.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        
        # 2. container.xml
        epub.writestr('META-INF/container.xml', '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>''')

        # 3. 各ページHTMLと画像、およびマニフェスト項目
        manifest_items = []
        spine_items = []
        
        # nav.xhtml
        nav_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>Navigation</title></head>
<body>
    <nav epub:type="toc"><h1>Table of Contents</h1><ol><li><a href="Text/p_001.xhtml">Start</a></li></ol></nav>
</body>
</html>'''
        epub.writestr('OEBPS/nav.xhtml', nav_content)
        manifest_items.append('<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>')

        for i, img_path in enumerate(image_paths):
            page_num = i + 1
            img_filename = os.path.basename(img_path)
            html_filename = f"p_{page_num:03d}.xhtml"
            img_id = f"img_{page_num:03d}"
            item_id = f"item_{page_num:03d}"
            
            # 画像のサイズ取得 (固定レイアウト用)
            with Image.open(img_path) as img:
                w, h = img.size
                
            # HTML生成
            html_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <meta name="viewport" content="width={w}, height={h}"/>
    <title>Page {page_num}</title>
    <style type="text/css">
        body {{ margin: 0; padding: 0; background-color: #000; }}
        img {{ width: {w}px; height: {h}px; }}
    </style>
</head>
<body>
    <div><img src="../Images/{img_filename}" alt="page {page_num}"/></div>
</body>
</html>'''
            epub.writestr(f"OEBPS/Text/{html_filename}", html_content)
            epub.write(img_path, f"OEBPS/Images/{img_filename}")
            
            img_media_type = "image/png" if os.path.splitext(img_filename)[1].lower() == ".png" else "image/jpeg"
            manifest_items.append(f'<item id="{item_id}" href="Text/{html_filename}" media-type="application/xhtml+xml"/>')
            manifest_items.append(f'<item id="{img_id}" href="Images/{img_filename}" media-type="{img_media_type}"/>')
            spine_items.append(f'<itemref idref="{item_id}"/>')

        # 4. content.opf
        manifest_str = "\n        ".join(manifest_items)
        spine_str = "\n        ".join(spine_items)
        
        opf_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:identifier id="pub-id">urn:uuid:{book_id}</dc:identifier>
        <dc:title>{escape(title)}</dc:title>
        <dc:creator>{escape(author)}</dc:creator>
        <dc:language>ja</dc:language>
        <meta property="dcterms:modified">{now}</meta>
        <meta property="rendition:layout">pre-paginated</meta>
        <meta property="rendition:orientation">auto</meta>
        <meta property="rendition:spread">auto</meta>
    </metadata>
    <manifest>
        {manifest_str}
    </manifest>
    <spine page-progression-direction="rtl">
        {spine_str}
    </spine>
</package>'''
        epub.writestr('OEBPS/content.opf', opf_content)

def batch_process(image_list: list[str], output_dir: str, max_width: int, max_height: int, prefix: str, use_grayscale: bool, bits: int,
                  use_rename: bool = True, force_jpeg: bool = False, epub_settings: Optional[dict] = None, xtc_settings: Optional[dict] = None,
                  alignment: str = "center", progress_callback: Optional[Callable[[int, int], None]] = None, log_callback: Optional[Callable[[str], None]] = None,
                  auto_split: bool = False, blur_strength: int = 0, contrast: int = 0,
                  crop_rects: dict | None = None, auto_rotate: bool = False, sharpen: int = 0, clahe: int = 0, no_resize: bool = False,
                  output_name: str = "", compress_format: str = "",
                  split_target: int = 0, split_order_h: int = 0) -> list[str]:
    """
    画像リストを並列処理し、保存する。
    Phase 1: 全タスクを逐次展開（画像読み込み・パス計算）
    Phase 2: ThreadPoolExecutor で元画像単位に並列実行
    Phase 3: 元画像順に結果を収集して EPUB/XTC へ渡す
    auto_split=True の場合は各画像を長辺側で2分割して出力する。
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    results: list[str] = []
    processed_paths: list[str] = []

    # EPUB/XTC有効時は一時フォルダで処理を行い、個別画像を出力フォルダに残さない
    is_epub_enabled = epub_settings and epub_settings.get("enabled")
    is_xtc_enabled = xtc_settings and xtc_settings.get("enabled")
    is_individual = not is_epub_enabled and not is_xtc_enabled

    # 一時フォルダを使用するためのコンテキストマネージャ
    temp_dir_obj = None
    actual_out_dir = output_dir

    if is_epub_enabled or is_xtc_enabled:
        temp_dir_obj = tempfile.TemporaryDirectory()
        actual_out_dir = temp_dir_obj.name
    elif is_individual:
        if compress_format:
            # zip/cbz の場合は一時フォルダで処理し後で圧縮
            temp_dir_obj = tempfile.TemporaryDirectory()
            actual_out_dir = temp_dir_obj.name
        elif output_name:
            # 出力名でサブフォルダを作成
            actual_out_dir = os.path.join(output_dir, output_name)
            os.makedirs(actual_out_dir, exist_ok=True)

    try:
        # --- Phase 1: タスクリストを逐次構築（画像読み込みとパス計算）---
        # task_groups[img_idx] = {'img_idx': int, 'sub_tasks': [sub_task, ...]}
        # sub_task キー: sub_img, target_path, orig_ext, xtc_format,
        #               dither_algo, dither_intensity, clean_intensity, clean_algo, is_jpeg
        task_groups: list[dict] = []
        global_idx = 0  # 全体連番（分割時は1元画像→2増える）

        for img_idx, file_path in enumerate(image_list):
            is_jpeg = force_jpeg or is_epub_enabled
            orig_ext = os.path.splitext(file_path)[1].lower()

            with Image.open(file_path) as raw_img:
                raw_img.load()  # ファイルクローズ前に読み込み
                if auto_split:
                    w, h = raw_img.size
                    is_landscape = (w >= h)
                    apply_split = (
                        split_target == 0  # 両方
                        or (split_target == 1 and is_landscape)   # 左右のみ
                        or (split_target == 2 and not is_landscape)  # 上下のみ
                    )
                    if apply_split and is_landscape:
                        # 横長 → 左右分割。順序は split_order_h で決定
                        left_img, right_img = split_image_left_right(raw_img)
                        if split_order_h == 1:  # 右→左
                            sub_images = [(right_img, "right"), (left_img, "left")]
                        else:                    # 左→右
                            sub_images = [(left_img, "left"), (right_img, "right")]
                    elif apply_split and not is_landscape:
                        # 縦長 → 上下分割。順序は上→下固定
                        top_img, bot_img = split_image_top_bottom(raw_img)
                        sub_images = [(top_img, "top"), (bot_img, "bot")]
                    else:
                        sub_images = [(raw_img.copy(), "")]
                else:
                    sub_images = [(raw_img.copy(), "")]

            sub_tasks: list[dict] = []
            # ファイル名 suffix は分割時のみ "_1"/"_2" を付与（内部キー suffix とは別）
            for sub_idx, (sub_img, suffix) in enumerate(sub_images, start=1):
                global_idx += 1
                file_suffix = f"_{sub_idx}" if suffix else ""

                # 拡張子・ディザ・クリーン設定の決定
                if is_xtc_enabled:
                    xtc_fmt = xtc_settings.get("ext_format", "XTG")
                    d_algo = xtc_settings.get("dither_algo", "None")
                    d_intens = xtc_settings.get("dither_intensity", 0)
                    c_intens = xtc_settings.get("clean_intensity", 0)
                    c_algo = xtc_settings.get("clean_algo", "Median")
                    ext = ".xtg" if xtc_fmt == "XTG" else ".xth"
                else:
                    xtc_fmt = None
                    d_algo = xtc_settings.get("dither_algo", "None") if xtc_settings else "None"
                    d_intens = xtc_settings.get("dither_intensity", 0) if xtc_settings else 0
                    c_intens = xtc_settings.get("clean_intensity", 0) if xtc_settings else 0
                    c_algo = xtc_settings.get("clean_algo", "Median") if xtc_settings else "Median"
                    ext = ".jpg" if is_jpeg else orig_ext

                # ファイル名の決定（分割時は _1 / _2 の数字 suffix を使用）
                if use_rename:
                    new_name = f"{prefix}_{global_idx:03d}{file_suffix}{ext}"
                else:
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    new_name = f"{base_name}{file_suffix}{ext}"

                # クロップ矩形の取得（トリミング有効時）
                crop_rect = None
                if crop_rects is not None:
                    crop_rect = crop_rects.get((file_path, suffix))
                    if crop_rect is None:
                        # 未検出分はその場で検出
                        crop_rect = detect_trim_rect(sub_img)

                sub_tasks.append({
                    "sub_img":         sub_img,
                    "target_path":     os.path.join(actual_out_dir, new_name),
                    "orig_ext":        orig_ext,
                    "xtc_format":      xtc_fmt,
                    "dither_algo":     d_algo,
                    "dither_intensity": d_intens,
                    "clean_intensity": c_intens,
                    "clean_algo":      c_algo,
                    "is_jpeg":         is_jpeg,
                    "file_path":       file_path,
                    "suffix":          suffix,
                    "crop_rect":       crop_rect,
                })

            task_groups.append({"img_idx": img_idx, "sub_tasks": sub_tasks})

        # --- Phase 2 & 3: 並列実行 → 元画像順に収集 ---

        def _process_group(group: dict) -> tuple[int, list[str]]:
            """一つの元画像グループ（サブ画像含む）を処理して保存済みパスリストを返す。"""
            paths: list[str] = []
            for st in group["sub_tasks"]:
                try:
                    p = resize_image(
                        "", st["target_path"],
                        max_width, max_height,
                        use_grayscale, bits,
                        st["is_jpeg"], st["xtc_format"],
                        alignment,
                        st["dither_algo"], st["dither_intensity"],
                        st["clean_intensity"], st["clean_algo"],
                        img_override=st["sub_img"],
                        orig_ext=st["orig_ext"],
                        blur_strength=blur_strength,
                        contrast=contrast,
                        crop_rect=st["crop_rect"],
                        auto_rotate=auto_rotate,
                        sharpen=sharpen,
                        clahe=clahe,
                        no_resize=no_resize,
                    )
                    if p:
                        paths.append(p)
                except Exception as e:
                    msg = f"Error processing {st['file_path']} ({st['suffix']}): {e}"
                    if log_callback:
                        log_callback(msg)
                    else:
                        print(msg)
            return group["img_idx"], paths

        n_workers = min(os.cpu_count() or 1, len(task_groups)) if task_groups else 1
        # 元画像順の結果スロット（インデックスで直接参照）
        ordered_results: list[list[str]] = [[] for _ in task_groups]
        completed_count = 0

        with ThreadPoolExecutor(max_workers=n_workers) as executor:
            future_map = {
                executor.submit(_process_group, tg): tg["img_idx"]
                for tg in task_groups
            }
            for future in as_completed(future_map):
                try:
                    img_idx, paths = future.result()
                    ordered_results[img_idx] = paths
                except Exception as e:
                    img_idx = future_map[future]
                    if log_callback:
                        log_callback(f"Error in image group {img_idx + 1}: {e}")
                completed_count += 1
                if progress_callback:
                    progress_callback(completed_count, len(image_list))

        # 元画像順にフラット化
        for paths in ordered_results:
            processed_paths.extend(paths)
            if is_individual and not compress_format:
                results.extend(paths)

        # 個別画像 + zip/cbz 圧縮
        if is_individual and compress_format and processed_paths:
            ext = ".zip" if compress_format == "zip" else ".cbz"
            archive_name = (output_name or "output") + ext
            archive_path = os.path.join(output_dir, archive_name)
            try:
                import zipfile as zf
                with zf.ZipFile(archive_path, "w", zf.ZIP_STORED) as z:
                    for p in processed_paths:
                        z.write(p, os.path.basename(p))
                results.append(archive_path)
            except Exception as e:
                msg = f"Error creating {compress_format.upper()}: {e}"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)

        # EPUB生成
        if is_epub_enabled and processed_paths:
            title = epub_settings.get("title", "Untitled")
            author = epub_settings.get("author", "Unknown")
            epub_name = f"{output_name}.epub" if output_name else f"[{author}] {title}.epub"
            epub_path = os.path.join(output_dir, epub_name)
            try:
                create_epub(processed_paths, epub_path, title, author)
                results.append(epub_path)
            except Exception as e:
                msg = f"Error creating EPUB: {e}"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                
        # XTC生成
        if is_xtc_enabled and processed_paths:
            title = xtc_settings.get("title", "Untitled")
            author = xtc_settings.get("author", "Unknown")
            direction = xtc_settings.get("direction", 1)
            xtc_format = xtc_settings.get("ext_format", "XTG")

            # XTH (2-bit) の場合は自動的に xtch、XTG (1-bit) の場合は xtc
            is_xtch = (xtc_format == "XTH")
            ext = "xtch" if is_xtch else "xtc"

            xtc_name = f"{output_name}.{ext}" if output_name else f"[{author}] {title}.{ext}"
            xtc_path = os.path.join(output_dir, xtc_name)
            try:
                create_xtc(processed_paths, xtc_path, title, author, direction, is_xtch)
                results.append(xtc_path)
            except Exception as e:
                msg = f"Error creating XTC: {e}"
                if log_callback:
                    log_callback(msg)
                else:
                    print(msg)
                
    finally:
        if temp_dir_obj:
            temp_dir_obj.cleanup()
            
    return results
