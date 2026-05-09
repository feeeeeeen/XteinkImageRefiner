import sys
import os

# numba JITキャッシュを安定パスに固定する。
# --onefile ビルドでは _MEIPASS が起動ごとに異なる一時ディレクトリになるため、
# そのままだとキャッシュが毎回破棄され起動時に再コンパイルが走る。
# setdefault により、既に環境変数が設定されている場合は上書きしない。
_numba_cache_dir = os.path.join(os.path.expanduser("~"), ".cache", "XteinkImageRefiner")
try:
    os.makedirs(_numba_cache_dir, exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", _numba_cache_dir)
except OSError:
    pass  # キャッシュ設定に失敗しても動作に影響しない（Numba が無効になるだけ）

import zipfile
import tempfile
import shutil
import re
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QFileDialog, QListWidget, QListWidgetItem,
                             QGroupBox, QSpinBox, QCheckBox, QProgressBar,
                             QMessageBox, QScrollArea, QSlider, QSplitter, QComboBox,
                             QStyle, QSizePolicy)
from PySide6.QtCore import Qt, QThread, Signal, QTimer, QSettings, QRectF
from PySide6.QtGui import QPixmap, QImage, QDragEnterEvent, QDropEvent, QPainter, QPen, QColor, QBrush
from image_processor import batch_process, apply_processing, apply_bit_dithering, apply_cv2_cleaning, Image

# ---------------------------------------------------------------------------
# 翻訳辞書 (ja / en)
# ---------------------------------------------------------------------------
_TRANSLATIONS = {
    # タイトル
    "title_settings":       {"ja": "Settings",                "en": "Settings"},
    # グループボックス
    "grp_input":            {"ja": "1. 読み込み",              "en": "1. Input"},
    "grp_preprocess":       {"ja": "2. 前処理",                "en": "2. Preprocess"},
    "grp_resize":           {"ja": "3. リサイズ",              "en": "3. Resize"},
    "grp_grayscale":        {"ja": "4. グレースケール",        "en": "4. Grayscale"},
    "grp_rename":           {"ja": "5. リネーム",              "en": "5. Rename"},
    "grp_output_name":      {"ja": "6. 出力ファイル/フォルダ名", "en": "6. Output Name"},
    "grp_format":           {"ja": "7. 保存形式",              "en": "7. Format"},
    "grp_xtc":              {"ja": "8. XTC 詳細設定",          "en": "8. XTC Settings"},
    "grp_list":             {"ja": "画像一覧 (ドラッグで並べ替え)",
                             "en": "Images (Drag to Reorder)"},
    "grp_preview":          {"ja": "プレビュー (ホイールズーム / ドラッグパン)",
                             "en": "Preview (Wheel Zoom / Drag Pan)"},
    # チェックボックス
    "chk_auto_split":       {"ja": "自動分割",                "en": "Auto Split"},
    "chk_auto_rotate":      {"ja": "自動回転",                "en": "Auto Rotate"},
    "chk_auto_trim":        {"ja": "余白自動トリミング",      "en": "Auto Trim"},
    "chk_no_resize":        {"ja": "リサイズなし",            "en": "No Resize"},
    "lbl_preset":           {"ja": "プリセット:",             "en": "Preset:"},
    "combo_preset_none":    {"ja": "なし",                    "en": "None"},
    "chk_enable":           {"ja": "有効にする",              "en": "Enable"},
    "chk_jpeg":             {"ja": "JPEG変換 (.jpg)",         "en": "JPEG Conv. (.jpg)"},
    "chk_per_folder":       {"ja": "フォルダごとに保存",      "en": "Save per Folder"},
    "chk_edit_name":        {"ja": "編集する",                "en": "Edit"},
    # ラベル
    "lbl_blur":             {"ja": "ぼかし強度:",             "en": "Blur:"},
    "lbl_max_w":            {"ja": "最大幅:",                 "en": "Max W:"},
    "lbl_max_h":            {"ja": "最大高さ:",               "en": "Max H:"},
    "lbl_align":            {"ja": "配置:",                   "en": "Align:"},
    "lbl_sharpen":          {"ja": "シャープ:",               "en": "Sharpen:"},
    "lbl_bits":             {"ja": "ビット数 (1-8):",         "en": "Bits (1-8):"},
    "lbl_dither_algo":      {"ja": "ディザ算法:",             "en": "Dither:"},
    "lbl_dither_int":       {"ja": "ディザ強度:",             "en": "Dither Int.:"},
    "lbl_contrast":         {"ja": "コントラスト:",           "en": "Contrast:"},
    "lbl_clahe":            {"ja": "CLAHE:",                  "en": "CLAHE:"},
    "lbl_prefix":           {"ja": "接頭語:",                 "en": "Prefix:"},
    "lbl_title":            {"ja": "タイトル:",               "en": "Title:"},
    "lbl_author":           {"ja": "著者名:",                 "en": "Author:"},
    "lbl_img_type":         {"ja": "画像形式:",               "en": "Img Type:"},
    "lbl_direction":        {"ja": "綴じ方向:",               "en": "Direction:"},
    "lbl_clean_type":       {"ja": "クリーンアップ種類:",     "en": "Cleanup:"},
    "lbl_bg_clean":         {"ja": "背景クリーンアップ:",     "en": "BG Cleanup:"},
    "lbl_zoom":             {"ja": "ズーム:",                 "en": "Zoom:"},
    # ボタン
    "btn_start":            {"ja": "一括処理を開始",          "en": "Start Batch"},
    "btn_sort_num":         {"ja": "数字昇順",                "en": "Num Sort"},
    "btn_sort_name":        {"ja": "名前順",                  "en": "Name Sort"},
    "btn_clear":            {"ja": "全消去",                  "en": "Clear All"},
    "btn_preprocess":       {"ja": "前処理",                  "en": "Preprocess"},
    "btn_output":           {"ja": "出力",                    "en": "Output"},
    "btn_first_page":       {"ja": "1番目",                   "en": "Page 1"},
    "btn_second_page":      {"ja": "2番目",                   "en": "Page 2"},
    "btn_split_target_both":{"ja": "両方",                    "en": "Both"},
    "btn_split_target_lr":  {"ja": "左右のみ",                "en": "L/R only"},
    "btn_split_target_tb":  {"ja": "上下のみ",                "en": "T/B only"},
    "btn_split_order_lr":   {"ja": "左→右",                   "en": "L→R"},
    "btn_split_order_rl":   {"ja": "右→左",                   "en": "R→L"},
    # コンボボックスアイテム
    "combo_center":         {"ja": "中央寄せ",                "en": "Center"},
    "combo_top":            {"ja": "上寄せ",                  "en": "Top"},
    "combo_individual":     {"ja": "個別画像 (JPEG/PNG)",     "en": "Images (JPEG/PNG)"},
    "combo_folder":         {"ja": "フォルダに出力",          "en": "Output to Folder"},
    "combo_dir_ltr":        {"ja": "左開き (L→R)",            "en": "Left (L→R)"},
    "combo_dir_rtl":        {"ja": "右開き (R→L)",            "en": "Right (R→L)"},
    "combo_dir_ttb":        {"ja": "縦送り (Top→Bottom)",     "en": "Vertical (T→B)"},
    # プレースホルダ・ツールチップ
    "ph_drop":              {"ja": "フォルダ/ZIP/画像をドロップ...",
                             "en": "Drop folder/ZIP/images..."},
    "tip_open":             {"ja": "フォルダ / ZIP / 画像ファイルを選択",
                             "en": "Select folder / ZIP / images"},
    "lbl_select_image":     {"ja": "画像を選択してください",  "en": "Select an image"},
    "lbl_updating":         {"ja": "⟳\n更新中...",            "en": "⟳\nUpdating..."},
    "lbl_updating_short":   {"ja": "⟳ 更新中...",             "en": "⟳ Updating..."},
    # ダイアログ・メッセージ
    "dlg_select_input":     {"ja": "フォルダ / ZIP / 画像ファイルを選択",
                             "en": "Select folder / ZIP / images"},
    "dlg_filter_images":    {"ja": "画像・ZIPファイル (*.jpg *.jpeg *.png *.bmp *.webp *.zip)",
                             "en": "Image/ZIP files (*.jpg *.jpeg *.png *.bmp *.webp *.zip)"},
    "dlg_filter_all":       {"ja": "すべてのファイル (*)",    "en": "All files (*)"},
    "dlg_select_output":    {"ja": "保存先フォルダを選択",    "en": "Select output folder"},
    "dlg_error":            {"ja": "エラー",                  "en": "Error"},
    "dlg_done":             {"ja": "完了",                    "en": "Done"},
    "msg_no_images":        {"ja": "処理対象の画像がありません。",
                             "en": "No images to process."},
    "msg_zip_fail":         {"ja": "ZIPの解凍に失敗しました: {e}",
                             "en": "Failed to extract ZIP: {e}"},
    "msg_preview_fail":     {"ja": "プレビュー不可: {e}",     "en": "Preview failed: {e}"},
    "msg_done":             {"ja": "{n} 件のアイテムを処理しました。",
                             "en": "{n} items processed."},
    "msg_errors":           {"ja": "\n\nエラー ({n} 件):\n",
                             "en": "\n\nErrors ({n}):\n"},
    "msg_sources":          {"ja": "{n} 個のソースを読み込み済み",
                             "en": "{n} sources loaded"},
    "msg_load_fail":        {"ja": "画像の読み込みに失敗しました: {e}",
                             "en": "Failed to load images: {e}"},
}

def _tr(key: str, lang: str = "ja", **kwargs) -> str:
    """翻訳キーから現在の言語の文字列を返す"""
    text = _TRANSLATIONS.get(key, {}).get(lang, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

def _sanitize_filename(name: str) -> str:
    """Windowsファイル名予約文字を '_' に置換し、末尾のドット/空白を除去する。
    空文字や全削除された場合は 'untitled' を返す。"""
    if not name:
        return "untitled"
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    sanitized = sanitized.rstrip('. ').strip()
    return sanitized or "untitled"

class ProcessingThread(QThread):
    progress = Signal(int, int)
    finished = Signal(list)
    log = Signal(str)

    def __init__(self, image_list, output_dir, max_width, max_height, prefix, use_grayscale, bits, use_rename, force_jpeg, epub_settings=None, xtc_settings=None, alignment="center", auto_split=False, blur_strength=0, contrast=0, crop_rects=None, auto_rotate=False, sharpen=0, clahe=0, no_resize=False, output_name="", compress_format="", source_labels=None, source_ids=None, per_folder=False, use_source_label=False, split_target=0, split_order_h=0):
        super().__init__()
        self.image_list = image_list
        self.output_dir = output_dir
        self.max_width = max_width
        self.max_height = max_height
        self.prefix = prefix
        self.use_grayscale = use_grayscale
        self.bits = bits
        self.use_rename = use_rename
        self.force_jpeg = force_jpeg
        self.epub_settings = epub_settings
        self.xtc_settings = xtc_settings
        self.alignment = alignment
        self.auto_split = auto_split
        self.blur_strength = blur_strength
        self.contrast = contrast
        self.crop_rects = crop_rects
        self.auto_rotate = auto_rotate
        self.sharpen = sharpen
        self.clahe = clahe
        self.no_resize = no_resize
        self.output_name = output_name
        self.compress_format = compress_format
        self.source_labels = source_labels  # image_list と同じ長さ。per_folder時の表示・出力名用
        self.source_ids = source_ids        # image_list と同じ長さ。グルーピングの一意識別子
        self.per_folder = per_folder
        self.use_source_label = use_source_label  # True の場合、グループラベルを出力名に使用（連番なし）
        self.split_target = split_target          # 自動分割の適用対象 (0=両方, 1=左右のみ, 2=上下のみ)
        self.split_order_h = split_order_h        # 横長分割の順序 (0=左→右, 1=右→左)

    def _group_by_source(self):
        """画像一覧の順序を保ったまま、ソースID単位でグループ化する。
        異なる場所にある同名フォルダ（同じラベル）も別ソースIDなら別グループとして扱う。
        戻り値: [(label, [path,...]), ...] (出現順)"""
        groups = {}  # source_id -> (label, [paths])
        order = []   # source_id の出現順
        ids = self.source_ids or []
        labels = self.source_labels or []
        for i, path in enumerate(self.image_list):
            sid = ids[i] if i < len(ids) else None
            label = labels[i] if i < len(labels) else ""
            # source_id が無い場合は label をフォールバックキーに使う
            key = sid if sid is not None else f"_lbl:{label}"
            if key not in groups:
                groups[key] = (label, [])
                order.append(key)
            groups[key][1].append(path)
        return [(groups[k][0], groups[k][1]) for k in order]

    def run(self):
        try:
            # フォルダごと保存が無効、もしくはソースが1つしかない場合は通常処理
            groups = self._group_by_source() if (self.per_folder and self.source_labels) else None
            if not groups or len(groups) <= 1:
                results = batch_process(
                    self.image_list, self.output_dir,
                    self.max_width, self.max_height,
                    self.prefix, self.use_grayscale, self.bits,
                    use_rename=self.use_rename,
                    force_jpeg=self.force_jpeg,
                    epub_settings=self.epub_settings,
                    xtc_settings=self.xtc_settings,
                    alignment=self.alignment,
                    progress_callback=self.progress.emit,
                    log_callback=self.log.emit,
                    auto_split=self.auto_split,
                    blur_strength=self.blur_strength,
                    contrast=self.contrast,
                    crop_rects=self.crop_rects,
                    auto_rotate=self.auto_rotate,
                    sharpen=self.sharpen,
                    clahe=self.clahe,
                    no_resize=self.no_resize,
                    output_name=self.output_name,
                    compress_format=self.compress_format,
                    split_target=self.split_target,
                    split_order_h=self.split_order_h
                )
            else:
                # グループごとに batch_process を呼び出し、進捗を全画像通算で発火する
                results = []
                total_imgs = len(self.image_list)
                processed_offset = [0]  # クロージャから書き換えるためリストでラップ

                def make_progress_cb():
                    base = processed_offset[0]
                    def cb(current, _total_in_group):
                        self.progress.emit(base + current, total_imgs)
                    return cb

                pad = max(3, len(str(len(groups))))
                for idx, (label, paths) in enumerate(groups, start=1):
                    if self.use_source_label:
                        # 編集無効時は各グループのソースラベルをそのまま使用（連番なし）
                        if not label:
                            self.log.emit(f"警告: ソースラベルが空のため連番 {idx:0{pad}d} を使用します")
                        group_output_name = _sanitize_filename(label or f"{idx:0{pad}d}")
                    else:
                        suffix = f"_{idx:0{pad}d}"
                        group_output_name = (self.output_name + suffix) if self.output_name else suffix.lstrip("_")
                    grp_results = batch_process(
                        paths, self.output_dir,
                        self.max_width, self.max_height,
                        self.prefix, self.use_grayscale, self.bits,
                        use_rename=self.use_rename,
                        force_jpeg=self.force_jpeg,
                        epub_settings=self.epub_settings,
                        xtc_settings=self.xtc_settings,
                        alignment=self.alignment,
                        progress_callback=make_progress_cb(),
                        log_callback=self.log.emit,
                        auto_split=self.auto_split,
                        blur_strength=self.blur_strength,
                        contrast=self.contrast,
                        crop_rects=self.crop_rects,
                        auto_rotate=self.auto_rotate,
                        sharpen=self.sharpen,
                        clahe=self.clahe,
                        no_resize=self.no_resize,
                        output_name=group_output_name,
                        compress_format=self.compress_format,
                        split_target=self.split_target,
                        split_order_h=self.split_order_h
                    )
                    results.extend(grp_results)
                    processed_offset[0] += len(paths)
                # 最終進捗を確実に100%に
                self.progress.emit(total_imgs, total_imgs)
        except Exception as e:
            self.log.emit(f"致命的なエラーが発生しました: {e}")
            results = []
        self.finished.emit(results)

class TrimDetectThread(QThread):
    """全画像の余白を一括検出するバックグラウンドスレッド"""
    detected = Signal(str, str, tuple)  # (abs_path, suffix, crop_rect)
    all_done = Signal()

    def __init__(self, image_paths: list[str], auto_split: bool, split_target: int = 0):
        super().__init__()
        self.image_paths = list(image_paths)
        self.auto_split = auto_split
        self.split_target = split_target  # 0=両方, 1=左右のみ, 2=上下のみ
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        from image_processor import detect_trim_rect_fast, split_image_top_bottom, split_image_left_right
        for full_path in self.image_paths:
            if self._abort:
                return
            try:
                with Image.open(full_path) as raw:
                    raw.load()
                    img = raw.copy()

                if self.auto_split:
                    w, h = img.size
                    is_landscape = (w >= h)
                    apply_split = (
                        self.split_target == 0  # 両方
                        or (self.split_target == 1 and is_landscape)   # 左右のみ
                        or (self.split_target == 2 and not is_landscape)  # 上下のみ
                    )
                    if apply_split and is_landscape:
                        left_img, right_img = split_image_left_right(img)
                        self.detected.emit(full_path, "left", detect_trim_rect_fast(left_img))
                        if self._abort:
                            return
                        self.detected.emit(full_path, "right", detect_trim_rect_fast(right_img))
                    elif apply_split and not is_landscape:
                        top_img, bot_img = split_image_top_bottom(img)
                        self.detected.emit(full_path, "top", detect_trim_rect_fast(top_img))
                        if self._abort:
                            return
                        self.detected.emit(full_path, "bot", detect_trim_rect_fast(bot_img))
                    else:
                        # 分割対象外: 分割しないので suffix="" で全体検出
                        self.detected.emit(full_path, "", detect_trim_rect_fast(img))
                else:
                    self.detected.emit(full_path, "", detect_trim_rect_fast(img))
            except Exception:
                pass  # 検出失敗は無視（プレビュー時にon-demand検出で補う）

        self.all_done.emit()

class DraggableListWidget(QListWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setSelectionMode(QListWidget.ExtendedSelection)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete:
            selected = self.selectedItems()
            if selected:
                self.blockSignals(True)
                try:
                    for item in selected:
                        self.takeItem(self.row(item))
                finally:
                    self.blockSignals(False)
                self.itemSelectionChanged.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event):
        if event.source() is not self:
            super().dropEvent(event)
            return

        # 選択中アイテムを移動先に一括挿入
        selected_rows = sorted([self.row(item) for item in self.selectedItems()])
        if not selected_rows:
            event.ignore()
            return

        target_row = self.indexAt(event.position().toPoint()).row()
        if target_row == -1:
            target_row = self.count()

        items_info = []
        for r in selected_rows:
            it = self.item(r)
            items_info.append((it.text(), it.data(Qt.UserRole), it.data(Qt.UserRole + 1),
                               it.data(Qt.UserRole + 2), it.data(Qt.UserRole + 3)))

        # 移動先の補正（上側にある選択アイテムを取り除くと行番号がずれるため）
        shift = sum(1 for r in selected_rows if r < target_row)
        insert_at = target_row - shift

        # シグナルをブロックして途中の itemSelectionChanged を抑制
        self.blockSignals(True)
        try:
            # 下から削除して行番号のずれを防ぐ
            for row in reversed(selected_rows):
                self.takeItem(row)

            for i, (text, data, src_label, rel_disp, src_id) in enumerate(items_info):
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, data)
                item.setData(Qt.UserRole + 1, src_label)
                item.setData(Qt.UserRole + 2, rel_disp)
                item.setData(Qt.UserRole + 3, src_id)
                self.insertItem(insert_at + i, item)

            self.clearSelection()
            for i in range(insert_at, insert_at + len(items_info)):
                self.item(i).setSelected(True)
        finally:
            self.blockSignals(False)

        # IgnoreAction を指定して Qt の InternalMove による自動削除を防ぐ
        event.setDropAction(Qt.IgnoreAction)
        event.accept()
        # 最終的な選択変更を通知
        self.itemSelectionChanged.emit()

class PreviewLabel(QLabel):
    zoomRequested = Signal(int)  # ズーム変更要求 (相対値または0でリセット)
    cropRectChanged = Signal(tuple)  # クロップ矩形がドラッグで変更されたとき
    cropDragFinished = Signal()  # クロップ矩形のドラッグ操作が完了したとき

    # ドラッグハンドルの種類
    HANDLE_NONE = 0
    HANDLE_TOP = 1
    HANDLE_BOTTOM = 2
    HANDLE_LEFT = 3
    HANDLE_RIGHT = 4
    HANDLE_TL = 5
    HANDLE_TR = 6
    HANDLE_BL = 7
    HANDLE_BR = 8
    HANDLE_TOLERANCE = 8  # ヒット判定の許容距離 (ピクセル)

    def __init__(self, scroll_area, parent=None):
        super().__init__(parent)
        self.scroll_area = scroll_area
        self.last_mouse_pos = None
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignCenter)

        # クロップモード状態
        self._crop_mode = False
        self._crop_rect = None       # (left, top, right, bottom) 画像ピクセル座標
        self._image_size = None      # (width, height) 生画像サイズ
        self._zoom = 1.0
        self._pixmap_offset = (0, 0) # alignment=center によるオフセット
        self._dragging_handle = self.HANDLE_NONE
        self._drag_start_rect = None
        self._drag_start_pos = None

    def set_crop_params(self, crop_rect, image_size, zoom):
        """ImageEditorApp から呼ばれる。クロップモードのパラメータ設定"""
        self._crop_mode = True
        self._crop_rect = crop_rect
        self._image_size = image_size
        self._zoom = zoom
        self._update_pixmap_offset()
        self.update()

    def clear_crop_mode(self):
        """クロップモードを解除"""
        self._crop_mode = False
        self._crop_rect = None
        self._image_size = None
        self._dragging_handle = self.HANDLE_NONE
        self.update()

    def _update_pixmap_offset(self):
        """pixmap の左上のウィジェット座標を計算"""
        pm = self.pixmap()
        if pm is None or pm.isNull():
            self._pixmap_offset = (0, 0)
            return
        pw, ph = pm.width(), pm.height()
        ww, wh = self.width(), self.height()
        ox = max(0, (ww - pw) // 2)
        oy = max(0, (wh - ph) // 2)
        self._pixmap_offset = (ox, oy)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_pixmap_offset()

    def _image_to_widget(self, ix, iy):
        """画像ピクセル座標 → ウィジェットローカル座標"""
        ox, oy = self._pixmap_offset
        return (ix * self._zoom + ox, iy * self._zoom + oy)

    def _widget_to_image(self, wx, wy):
        """ウィジェットローカル座標 → 画像ピクセル座標"""
        ox, oy = self._pixmap_offset
        return ((wx - ox) / self._zoom, (wy - oy) / self._zoom)

    def _hit_test_handle(self, pos):
        """マウス位置がどのハンドルに近いか判定"""
        if self._crop_rect is None or self._image_size is None:
            return self.HANDLE_NONE

        l, t, r, b = self._crop_rect
        wl, wt = self._image_to_widget(l, t)
        wr, wb = self._image_to_widget(r, b)
        mx, my = pos.x(), pos.y()
        tol = self.HANDLE_TOLERANCE

        # コーナー判定（辺より優先）
        corners = [
            (wl, wt, self.HANDLE_TL), (wr, wt, self.HANDLE_TR),
            (wl, wb, self.HANDLE_BL), (wr, wb, self.HANDLE_BR),
        ]
        for cx, cy, handle in corners:
            if abs(mx - cx) <= tol and abs(my - cy) <= tol:
                return handle

        # 辺判定
        if abs(mx - wl) <= tol and wt - tol <= my <= wb + tol:
            return self.HANDLE_LEFT
        if abs(mx - wr) <= tol and wt - tol <= my <= wb + tol:
            return self.HANDLE_RIGHT
        if abs(my - wt) <= tol and wl - tol <= mx <= wr + tol:
            return self.HANDLE_TOP
        if abs(my - wb) <= tol and wl - tol <= mx <= wr + tol:
            return self.HANDLE_BOTTOM

        return self.HANDLE_NONE

    def paintEvent(self, event):
        super().paintEvent(event)

        if not self._crop_mode or self._crop_rect is None or self._image_size is None:
            return

        pm = self.pixmap()
        if pm is None or pm.isNull():
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        l, t, r, b = self._crop_rect
        iw, ih = self._image_size

        # 画像ピクセル座標 → ウィジェット座標
        wl, wt = self._image_to_widget(l, t)
        wr, wb = self._image_to_widget(r, b)
        w0, h0 = self._image_to_widget(0, 0)
        w1, h1 = self._image_to_widget(iw, ih)

        # 外側を半透明黒でディム
        dim_color = QColor(0, 0, 0, 128)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(dim_color))
        painter.drawRect(QRectF(w0, h0, w1 - w0, wt - h0))       # 上
        painter.drawRect(QRectF(w0, wb, w1 - w0, h1 - wb))       # 下
        painter.drawRect(QRectF(w0, wt, wl - w0, wb - wt))       # 左
        painter.drawRect(QRectF(wr, wt, w1 - wr, wb - wt))       # 右

        # 赤い矩形
        pen = QPen(QColor(255, 0, 0), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(QRectF(wl, wt, wr - wl, wb - wt))

        # コーナーハンドル（6×6 の赤い正方形）
        hs = 3
        painter.setBrush(QBrush(QColor(255, 0, 0)))
        painter.setPen(Qt.NoPen)
        for hx, hy in [(wl, wt), (wr, wt), (wl, wb), (wr, wb)]:
            painter.drawRect(QRectF(hx - hs, hy - hs, hs * 2, hs * 2))

        painter.end()

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoomRequested.emit(10)
        else:
            self.zoomRequested.emit(-10)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.zoomRequested.emit(0)
        event.accept()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # クロップモード時はハンドルのドラッグを優先
            if self._crop_mode and self._crop_rect is not None:
                handle = self._hit_test_handle(event.position())
                if handle != self.HANDLE_NONE:
                    self._dragging_handle = handle
                    self._drag_start_rect = self._crop_rect
                    self._drag_start_pos = event.position().toPoint()
                    event.accept()
                    return
            # パン操作
            self.last_mouse_pos = event.globalPosition().toPoint()
            self.setCursor(Qt.ClosedHandCursor)
        event.accept()

    def mouseMoveEvent(self, event):
        # ドラッグ中: クロップ矩形を更新
        if self._dragging_handle != self.HANDLE_NONE:
            self._update_crop_drag(event.position().toPoint())
            event.accept()
            return

        # ホバー時のカーソル変更
        if self._crop_mode and self._crop_rect is not None and self.last_mouse_pos is None:
            handle = self._hit_test_handle(event.position())
            cursor_map = {
                self.HANDLE_NONE: Qt.ArrowCursor,
                self.HANDLE_TOP: Qt.SizeVerCursor,
                self.HANDLE_BOTTOM: Qt.SizeVerCursor,
                self.HANDLE_LEFT: Qt.SizeHorCursor,
                self.HANDLE_RIGHT: Qt.SizeHorCursor,
                self.HANDLE_TL: Qt.SizeFDiagCursor,
                self.HANDLE_BR: Qt.SizeFDiagCursor,
                self.HANDLE_TR: Qt.SizeBDiagCursor,
                self.HANDLE_BL: Qt.SizeBDiagCursor,
            }
            self.setCursor(cursor_map.get(handle, Qt.ArrowCursor))

        # パン操作
        if self.last_mouse_pos is not None:
            current_pos = event.globalPosition().toPoint()
            delta = current_pos - self.last_mouse_pos
            self.last_mouse_pos = current_pos
            h_bar = self.scroll_area.horizontalScrollBar()
            v_bar = self.scroll_area.verticalScrollBar()
            h_bar.setValue(h_bar.value() - delta.x())
            v_bar.setValue(v_bar.value() - delta.y())
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging_handle != self.HANDLE_NONE:
            self._dragging_handle = self.HANDLE_NONE
            self._drag_start_rect = None
            self._drag_start_pos = None
            self.cropDragFinished.emit()
            event.accept()
            return
        self.last_mouse_pos = None
        self.setCursor(Qt.ArrowCursor)
        event.accept()

    def _update_crop_drag(self, current_pos):
        """ドラッグ中のクロップ矩形更新"""
        if self._drag_start_rect is None or self._drag_start_pos is None or self._image_size is None:
            return

        dx_widget = current_pos.x() - self._drag_start_pos.x()
        dy_widget = current_pos.y() - self._drag_start_pos.y()
        dx_img = dx_widget / self._zoom
        dy_img = dy_widget / self._zoom

        sl, st, sr, sb = self._drag_start_rect
        l, t, r, b = sl, st, sr, sb
        iw, ih = self._image_size
        MIN_SIZE = 10

        handle = self._dragging_handle

        if handle in (self.HANDLE_TOP, self.HANDLE_TL, self.HANDLE_TR):
            t = max(0, min(b - MIN_SIZE, int(st + dy_img)))
        if handle in (self.HANDLE_BOTTOM, self.HANDLE_BL, self.HANDLE_BR):
            b = min(ih, max(t + MIN_SIZE, int(sb + dy_img)))
        if handle in (self.HANDLE_LEFT, self.HANDLE_TL, self.HANDLE_BL):
            l = max(0, min(r - MIN_SIZE, int(sl + dx_img)))
        if handle in (self.HANDLE_RIGHT, self.HANDLE_TR, self.HANDLE_BR):
            r = min(iw, max(l + MIN_SIZE, int(sr + dx_img)))

        self._crop_rect = (l, t, r, b)
        self.update()
        self.cropRectChanged.emit(self._crop_rect)

class ImageEditorApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xteink Image Refiner")

        self.current_preview_image = None
        self._temp_dirs: list[str] = []
        self._preview_running = False  # 再入防止フラグ
        self._error_log = []

        # 余白トリミング用のクロップ矩形ストア
        # キー: (filename, suffix) where suffix = "" | "top" | "bot"
        # 値: (left, top, right, bottom) in post-split/rotate image pixel coords
        self.crop_rects: dict[tuple[str, str], tuple[int, int, int, int]] = {}
        self._current_crop_key: tuple[str, str] | None = None
        self._current_raw_preview = None  # クロップ座標系の生画像
        self._split_preview_half: str = "first"  # 分割プレビュー対象 ("first"=上/左, "second"=下/右)
        self._trim_detect_thread = None
        self._preview_mode: str = "output"  # "preprocess" | "output"
        self._lang: str = "ja"  # 現在の言語 ("ja" | "en")
        self._next_source_id: int = 0  # 各ソース読み込みに割り当てる一意なID
        self._split_target: int = 0    # 自動分割の適用対象 (0=両方, 1=左右のみ, 2=上下のみ)
        self._split_order_h: int = 0   # 横長分割の順序 (0=左→右, 1=右→左)

        # プレビュー更新デバウンスタイマー (300ms)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self.refresh_preview)

        # UI初期化
        self.init_ui()

        # スタイル適用（フォントサイズが確定する）
        self.load_stylesheet()

        # 前回の設定を復元
        self.load_settings()

        # ドラッグ＆ドロップの許可
        self.setAcceptDrops(True)

        # -----------------------------------------------------------
        # 最小ウィンドウ高さを設定ペインの自然サイズから計算する。
        # 全グループ表示時（最大構成）の高さを基準にし、
        # UIが隠れない最小サイズを保証する。
        # -----------------------------------------------------------
        for child in self._settings_widget.findChildren(QWidget):
            child.ensurePolished()
        self._settings_widget.ensurePolished()

        # 全グループ表示状態でサイズを計測（XTCグループの表示状態を一時変更）
        # isVisible() はウィンドウ show() 前は親が非表示のため常に False を返す。
        # isHidden() はウィジェット自体の setVisible 状態を返すため正確。
        xtc_was_hidden = self.xtc_group.isHidden()
        self.xtc_group.setVisible(True)
        CHROME_H = 10  # タイトルバー + ウィンドウ枠 + マージン
        hint = self._settings_widget.sizeHint()
        min_h = hint.height() + CHROME_H
        # 設定ペインの幅を最大構成時で固定（XTC表示切替で幅が変わらないようにする）
        self._settings_widget.setFixedWidth(hint.width())
        self.xtc_group.setVisible(not xtc_was_hidden)

        self.setMinimumSize(1200, min_h)
        self.resize(1280, min_h)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(3, 3, 3, 3)
        
        splitter = QSplitter(Qt.Horizontal)
        
        # --- ペイン1: 設定 (Settings) ---
        settings_widget = QWidget()
        self._settings_widget = settings_widget
        settings_layout = QVBoxLayout(settings_widget)
        settings_layout.setContentsMargins(3, 3, 3, 3)
        settings_layout.setSpacing(1)

        title_row = QHBoxLayout()
        self._title_label = QLabel(_tr("title_settings", self._lang))
        self._title_label.setObjectName("titleLabel")
        title_row.addWidget(self._title_label)
        title_row.addStretch()
        self._lang_combo = QComboBox()
        self._lang_combo.addItems(["Japanese", "English"])
        self._lang_combo.setFixedWidth(90)
        self._lang_combo.currentIndexChanged.connect(self._on_language_changed)
        title_row.addWidget(self._lang_combo)
        settings_layout.addLayout(title_row)

        # 翻訳対象ウィジェット登録リスト: (widget, method, tr_key)
        self._tr_widgets: list[tuple] = []

        # 1. 読み込み
        self._load_group = QGroupBox(_tr("grp_input", self._lang))
        load_vbox = QVBoxLayout(self._load_group)
        load_vbox.setContentsMargins(4, 1, 4, 2)
        load_vbox.setSpacing(2)

        load_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(_tr("ph_drop", self._lang))
        self.path_edit.setReadOnly(True)
        load_row.addWidget(self.path_edit)
        self._open_btn = QPushButton()
        self._open_btn.setObjectName("iconButton")
        self._open_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
        self._open_btn.setToolTip(_tr("tip_open", self._lang))
        self._open_btn.clicked.connect(self.select_input)
        load_row.addWidget(self._open_btn)
        load_vbox.addLayout(load_row)
        settings_layout.addWidget(self._load_group)

        # 2. 前処理
        self._preproc_group = QGroupBox(_tr("grp_preprocess", self._lang))
        preproc_vbox = QVBoxLayout(self._preproc_group)
        preproc_vbox.setContentsMargins(4, 1, 4, 2)
        preproc_vbox.setSpacing(2)
        split_row = QHBoxLayout()
        split_row.setContentsMargins(0, 0, 0, 0)
        split_row.setSpacing(6)
        self.split_check = QCheckBox(_tr("chk_auto_split", self._lang))
        self.split_check.stateChanged.connect(self._on_split_changed)
        split_row.addWidget(self.split_check)
        # 自動分割の適用対象トグル（両方 / 左右のみ / 上下のみ）
        self.split_target_btn = QPushButton(_tr("btn_split_target_both", self._lang))
        self.split_target_btn.setObjectName("compactToggleButton")
        self.split_target_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.split_target_btn.clicked.connect(self._on_split_target_toggle)
        split_row.addWidget(self.split_target_btn)
        # 左右分割の順序トグル（左→右 / 右→左）
        self.split_order_btn = QPushButton(_tr("btn_split_order_lr", self._lang))
        self.split_order_btn.setObjectName("compactToggleButton")
        self.split_order_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.split_order_btn.clicked.connect(self._on_split_order_toggle)
        split_row.addWidget(self.split_order_btn)
        self._update_split_btn_widths()
        split_row.addStretch()
        preproc_vbox.addLayout(split_row)
        self.auto_rotate_check = QCheckBox(_tr("chk_auto_rotate", self._lang))
        self.auto_rotate_check.stateChanged.connect(self.refresh_preview)
        preproc_vbox.addWidget(self.auto_rotate_check)
        self.trim_check = QCheckBox(_tr("chk_auto_trim", self._lang))
        self.trim_check.stateChanged.connect(self._on_trim_changed)
        preproc_vbox.addWidget(self.trim_check)
        blur_layout = QHBoxLayout()
        self._blur_label = QLabel(_tr("lbl_blur", self._lang))
        blur_layout.addWidget(self._blur_label)
        self.blur_slider = QSlider(Qt.Horizontal)
        self.blur_slider.setRange(0, 100)
        self.blur_slider.setValue(0)
        self.blur_slider.sliderReleased.connect(self.refresh_preview)
        blur_layout.addWidget(self.blur_slider)
        self.blur_spin = QSpinBox()
        self.blur_spin.setRange(0, 100)
        self.blur_spin.setValue(0)
        self.blur_spin.setSuffix("%")
        self.blur_spin.setFixedWidth(60)
        blur_layout.addWidget(self.blur_spin)
        preproc_vbox.addLayout(blur_layout)
        self.blur_slider.valueChanged.connect(
            lambda v: (self.blur_spin.blockSignals(True), self.blur_spin.setValue(v), self.blur_spin.blockSignals(False))
        )
        self.blur_spin.valueChanged.connect(
            lambda v: (self.blur_slider.blockSignals(True), self.blur_slider.setValue(v), self.blur_slider.blockSignals(False), self._start_preview_timer())
        )
        self.blur_spin.editingFinished.connect(self.refresh_preview)
        settings_layout.addWidget(self._preproc_group)

        # 3. リサイズ設定
        self._resize_group = QGroupBox(_tr("grp_resize", self._lang))
        resize_grid = QVBoxLayout(self._resize_group)
        resize_grid.setContentsMargins(4, 1, 4, 2)
        resize_grid.setSpacing(2)

        self.no_resize_check = QCheckBox(_tr("chk_no_resize", self._lang))
        self.no_resize_check.toggled.connect(self.on_no_resize_changed)
        resize_grid.addWidget(self.no_resize_check)

        preset_layout = QHBoxLayout()
        self._preset_label = QLabel(_tr("lbl_preset", self._lang))
        preset_layout.addWidget(self._preset_label)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([
            _tr("combo_preset_none", self._lang),
            "Xteink X3 (528×792)",
            "Xteink X4 (480×800)",
            "M5Paper S3 (540×960)",
        ])
        self.preset_combo.currentIndexChanged.connect(self.on_preset_changed)
        preset_layout.addWidget(self.preset_combo)
        resize_grid.addLayout(preset_layout)

        w_layout = QHBoxLayout()
        self.width_label = QLabel(_tr("lbl_max_w", self._lang))
        w_layout.addWidget(self.width_label)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 10000)
        self.width_spin.setValue(1920)
        self.width_spin.valueChanged.connect(self.refresh_preview)
        w_layout.addWidget(self.width_spin)
        resize_grid.addLayout(w_layout)

        h_layout = QHBoxLayout()
        self.height_label = QLabel(_tr("lbl_max_h", self._lang))
        h_layout.addWidget(self.height_label)
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 10000)
        self.height_spin.setValue(1080)
        self.height_spin.valueChanged.connect(self.refresh_preview)
        h_layout.addWidget(self.height_spin)
        resize_grid.addLayout(h_layout)

        al_layout = QHBoxLayout()
        self.alignment_label = QLabel(_tr("lbl_align", self._lang))
        al_layout.addWidget(self.alignment_label)
        self.alignment_combo = QComboBox()
        self.alignment_combo.addItems([_tr("combo_center", self._lang), _tr("combo_top", self._lang)])
        self.alignment_combo.currentIndexChanged.connect(self.refresh_preview)
        al_layout.addWidget(self.alignment_combo)
        resize_grid.addLayout(al_layout)

        sharpen_layout = QHBoxLayout()
        self.sharpen_label = QLabel(_tr("lbl_sharpen", self._lang))
        sharpen_layout.addWidget(self.sharpen_label)
        self.sharpen_slider = QSlider(Qt.Horizontal)
        self.sharpen_slider.setRange(0, 100)
        self.sharpen_slider.setValue(0)
        self.sharpen_slider.sliderReleased.connect(self.refresh_preview)
        sharpen_layout.addWidget(self.sharpen_slider)
        self.sharpen_spin = QSpinBox()
        self.sharpen_spin.setRange(0, 100)
        self.sharpen_spin.setValue(0)
        self.sharpen_spin.setSuffix("%")
        self.sharpen_spin.setFixedWidth(60)
        sharpen_layout.addWidget(self.sharpen_spin)
        resize_grid.addLayout(sharpen_layout)
        self.sharpen_slider.valueChanged.connect(
            lambda v: (self.sharpen_spin.blockSignals(True), self.sharpen_spin.setValue(v), self.sharpen_spin.blockSignals(False))
        )
        self.sharpen_spin.valueChanged.connect(
            lambda v: (self.sharpen_slider.blockSignals(True), self.sharpen_slider.setValue(v), self.sharpen_slider.blockSignals(False), self._start_preview_timer())
        )
        self.sharpen_spin.editingFinished.connect(self.refresh_preview)

        settings_layout.addWidget(self._resize_group)

        # 4. グレースケール
        self._gray_group = QGroupBox(_tr("grp_grayscale", self._lang))
        gray_vbox = QVBoxLayout(self._gray_group)
        gray_vbox.setContentsMargins(4, 1, 4, 2)
        gray_vbox.setSpacing(2)
        self.gray_check = QCheckBox(_tr("chk_enable", self._lang))
        self.gray_check.toggled.connect(self.on_gray_changed)
        gray_vbox.addWidget(self.gray_check)

        b_layout = QHBoxLayout()
        self.bits_label = QLabel(_tr("lbl_bits", self._lang))
        b_layout.addWidget(self.bits_label)
        self.bits_spin = QSpinBox()
        self.bits_spin.setRange(1, 8)
        self.bits_spin.setValue(8)
        self.bits_spin.valueChanged.connect(self.refresh_preview)
        b_layout.addWidget(self.bits_spin)
        gray_vbox.addLayout(b_layout)

        algo_layout = QHBoxLayout()
        self.dither_algo_label = QLabel(_tr("lbl_dither_algo", self._lang))
        algo_layout.addWidget(self.dither_algo_label)
        self.dither_algo_combo = QComboBox()
        self.dither_algo_combo.addItems(["None", "Floyd-Steinberg", "Atkinson", "Sauvola"])
        self.dither_algo_combo.currentIndexChanged.connect(self.refresh_preview)
        algo_layout.addWidget(self.dither_algo_combo)
        gray_vbox.addLayout(algo_layout)

        dz_layout = QHBoxLayout()
        self.dither_intensity_label = QLabel(_tr("lbl_dither_int", self._lang))
        dz_layout.addWidget(self.dither_intensity_label)
        self.dither_slider = QSlider(Qt.Horizontal)
        self.dither_slider.setRange(0, 100)
        self.dither_slider.setValue(0)
        self.dither_slider.sliderReleased.connect(self.refresh_preview)
        dz_layout.addWidget(self.dither_slider)
        self.dither_spin = QSpinBox()
        self.dither_spin.setRange(0, 100)
        self.dither_spin.setValue(0)
        self.dither_spin.setSuffix("%")
        self.dither_spin.setFixedWidth(60)
        dz_layout.addWidget(self.dither_spin)
        gray_vbox.addLayout(dz_layout)
        # スライダー ↔ スピンボックス 双方向同期
        # slider→spinbox: シグナルをブロックしてタイマーが起動しないようにする
        self.dither_slider.valueChanged.connect(
            lambda v: (self.dither_spin.blockSignals(True), self.dither_spin.setValue(v), self.dither_spin.blockSignals(False))
        )
        # spinbox→slider: スライダーをブロックし、タイマーでプレビュー更新（矢印ボタン対応）
        self.dither_spin.valueChanged.connect(
            lambda v: (self.dither_slider.blockSignals(True), self.dither_slider.setValue(v), self.dither_slider.blockSignals(False), self._start_preview_timer())
        )
        self.dither_spin.editingFinished.connect(self.refresh_preview)

        ct_layout = QHBoxLayout()
        self.contrast_label = QLabel(_tr("lbl_contrast", self._lang))
        ct_layout.addWidget(self.contrast_label)
        self.contrast_slider = QSlider(Qt.Horizontal)
        self.contrast_slider.setRange(0, 100)
        self.contrast_slider.setValue(0)
        self.contrast_slider.sliderReleased.connect(self.refresh_preview)
        ct_layout.addWidget(self.contrast_slider)
        self.contrast_spin = QSpinBox()
        self.contrast_spin.setRange(0, 100)
        self.contrast_spin.setValue(0)
        self.contrast_spin.setSuffix("%")
        self.contrast_spin.setFixedWidth(60)
        ct_layout.addWidget(self.contrast_spin)
        gray_vbox.addLayout(ct_layout)
        self.contrast_slider.valueChanged.connect(
            lambda v: (self.contrast_spin.blockSignals(True), self.contrast_spin.setValue(v), self.contrast_spin.blockSignals(False))
        )
        self.contrast_spin.valueChanged.connect(
            lambda v: (self.contrast_slider.blockSignals(True), self.contrast_slider.setValue(v), self.contrast_slider.blockSignals(False), self._start_preview_timer())
        )
        self.contrast_spin.editingFinished.connect(self.refresh_preview)

        clahe_layout = QHBoxLayout()
        self.clahe_label = QLabel(_tr("lbl_clahe", self._lang))
        clahe_layout.addWidget(self.clahe_label)
        self.clahe_slider = QSlider(Qt.Horizontal)
        self.clahe_slider.setRange(0, 100)
        self.clahe_slider.setValue(0)
        self.clahe_slider.sliderReleased.connect(self.refresh_preview)
        clahe_layout.addWidget(self.clahe_slider)
        self.clahe_spin = QSpinBox()
        self.clahe_spin.setRange(0, 100)
        self.clahe_spin.setValue(0)
        self.clahe_spin.setSuffix("%")
        self.clahe_spin.setFixedWidth(60)
        clahe_layout.addWidget(self.clahe_spin)
        gray_vbox.addLayout(clahe_layout)
        self.clahe_slider.valueChanged.connect(
            lambda v: (self.clahe_spin.blockSignals(True), self.clahe_spin.setValue(v), self.clahe_spin.blockSignals(False))
        )
        self.clahe_spin.valueChanged.connect(
            lambda v: (self.clahe_slider.blockSignals(True), self.clahe_slider.setValue(v), self.clahe_slider.blockSignals(False), self._start_preview_timer())
        )
        self.clahe_spin.editingFinished.connect(self.refresh_preview)

        # グレースケールOFF時はサブ設定を初期無効化
        for w in [self.bits_label, self.bits_spin,
                  self.dither_algo_label, self.dither_algo_combo,
                  self.dither_intensity_label, self.dither_slider, self.dither_spin,
                  self.contrast_label, self.contrast_slider, self.contrast_spin,
                  self.clahe_label, self.clahe_slider, self.clahe_spin]:
            w.setEnabled(False)

        settings_layout.addWidget(self._gray_group)

        # 5. リネーム
        self._rename_group = QGroupBox(_tr("grp_rename", self._lang))
        rename_vbox = QVBoxLayout(self._rename_group)
        rename_vbox.setContentsMargins(4, 1, 4, 2)
        rename_vbox.setSpacing(2)
        self.rename_check = QCheckBox(_tr("chk_enable", self._lang))
        self.rename_check.setChecked(True)
        rename_vbox.addWidget(self.rename_check)

        pre_layout = QHBoxLayout()
        self._prefix_label = QLabel(_tr("lbl_prefix", self._lang))
        pre_layout.addWidget(self._prefix_label)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setText("image")
        pre_layout.addWidget(self.prefix_edit)
        rename_vbox.addLayout(pre_layout)
        settings_layout.addWidget(self._rename_group)

        # 6. 出力ファイル/フォルダ名
        self.output_name_group = QGroupBox(_tr("grp_output_name", self._lang))
        output_name_vbox = QVBoxLayout(self.output_name_group)
        output_name_vbox.setContentsMargins(4, 1, 4, 2)
        output_name_vbox.setSpacing(2)

        self.edit_name_check = QCheckBox(_tr("chk_edit_name", self._lang))
        self.edit_name_check.setChecked(True)
        self.edit_name_check.toggled.connect(self.on_edit_name_changed)
        output_name_vbox.addWidget(self.edit_name_check)

        t_layout = QHBoxLayout()
        self._title_label2 = QLabel(_tr("lbl_title", self._lang))
        t_layout.addWidget(self._title_label2)
        self.epub_title_edit = QLineEdit()
        t_layout.addWidget(self.epub_title_edit)
        output_name_vbox.addLayout(t_layout)

        a_layout = QHBoxLayout()
        self._author_label = QLabel(_tr("lbl_author", self._lang))
        a_layout.addWidget(self._author_label)
        self.epub_author_edit = QLineEdit()
        a_layout.addWidget(self.epub_author_edit)
        output_name_vbox.addLayout(a_layout)

        self.output_name_preview = QLabel("")
        self.output_name_preview.setWordWrap(True)
        self.output_name_preview.setStyleSheet("color: #888;")
        output_name_vbox.addWidget(self.output_name_preview)

        # タイトル・著者名の変更で出力名プレビューを更新
        self.epub_title_edit.textChanged.connect(self._update_output_name_preview)
        self.epub_author_edit.textChanged.connect(self._update_output_name_preview)

        settings_layout.addWidget(self.output_name_group)

        # 7. 保存形式
        self._format_group = QGroupBox(_tr("grp_format", self._lang))
        format_vbox = QVBoxLayout(self._format_group)
        format_vbox.setContentsMargins(4, 1, 4, 2)
        format_vbox.setSpacing(2)

        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems([_tr("combo_individual", self._lang), "EPUB3", "XTC / XTCH"])
        self.output_format_combo.currentIndexChanged.connect(self.on_format_changed)
        format_vbox.addWidget(self.output_format_combo)

        self.jpeg_check = QCheckBox(_tr("chk_jpeg", self._lang))
        format_vbox.addWidget(self.jpeg_check)

        # 個別画像用: 圧縮オプション
        self.compress_combo = QComboBox()
        self.compress_combo.addItems([_tr("combo_folder", self._lang), "ZIP (.zip)", "CBZ (.cbz)"])
        self.compress_combo.currentIndexChanged.connect(self._update_output_name_preview)
        format_vbox.addWidget(self.compress_combo)

        self.per_folder_check = QCheckBox(_tr("chk_per_folder", self._lang))
        format_vbox.addWidget(self.per_folder_check)

        settings_layout.addWidget(self._format_group)

        # 8. XTC 詳細設定
        self.xtc_group = QGroupBox(_tr("grp_xtc", self._lang))
        self.xtc_group.setVisible(False)
        xtc_vbox = QVBoxLayout(self.xtc_group)
        xtc_vbox.setContentsMargins(4, 1, 4, 2)
        xtc_vbox.setSpacing(2)

        xb_layout = QHBoxLayout()
        self._img_type_label = QLabel(_tr("lbl_img_type", self._lang))
        xb_layout.addWidget(self._img_type_label)
        self.xtc_bit_combo = QComboBox()
        self.xtc_bit_combo.addItems(["XTG (1-bit)", "XTH (2-bit)"])
        self.xtc_bit_combo.currentIndexChanged.connect(self.refresh_preview)
        self.xtc_bit_combo.currentIndexChanged.connect(self._update_output_name_preview)
        xb_layout.addWidget(self.xtc_bit_combo)
        xtc_vbox.addLayout(xb_layout)

        dir_layout = QHBoxLayout()
        self._dir_label = QLabel(_tr("lbl_direction", self._lang))
        dir_layout.addWidget(self._dir_label)
        self.xtc_dir_combo = QComboBox()
        self.xtc_dir_combo.addItems([_tr("combo_dir_ltr", self._lang), _tr("combo_dir_rtl", self._lang), _tr("combo_dir_ttb", self._lang)])
        dir_layout.addWidget(self.xtc_dir_combo)
        xtc_vbox.addLayout(dir_layout)

        cl_type_layout = QHBoxLayout()
        self._clean_type_label = QLabel(_tr("lbl_clean_type", self._lang))
        cl_type_layout.addWidget(self._clean_type_label)
        self.clean_algo_combo = QComboBox()
        self.clean_algo_combo.addItems(["Median", "Bilateral"])
        self.clean_algo_combo.currentIndexChanged.connect(self.refresh_preview)
        cl_type_layout.addWidget(self.clean_algo_combo)
        xtc_vbox.addLayout(cl_type_layout)

        cl_layout = QHBoxLayout()
        self._bg_clean_label = QLabel(_tr("lbl_bg_clean", self._lang))
        cl_layout.addWidget(self._bg_clean_label)
        self.clean_slider = QSlider(Qt.Horizontal)
        self.clean_slider.setRange(0, 100)
        self.clean_slider.setValue(0)
        self.clean_slider.sliderReleased.connect(self.refresh_preview)
        cl_layout.addWidget(self.clean_slider)
        self.clean_spin = QSpinBox()
        self.clean_spin.setRange(0, 100)
        self.clean_spin.setValue(0)
        self.clean_spin.setSuffix("%")
        self.clean_spin.setFixedWidth(60)
        cl_layout.addWidget(self.clean_spin)
        xtc_vbox.addLayout(cl_layout)
        # スライダー ↔ スピンボックス 双方向同期
        # slider→spinbox: シグナルをブロックしてタイマーが起動しないようにする
        self.clean_slider.valueChanged.connect(
            lambda v: (self.clean_spin.blockSignals(True), self.clean_spin.setValue(v), self.clean_spin.blockSignals(False))
        )
        # spinbox→slider: スライダーをブロックし、タイマーでプレビュー更新（矢印ボタン対応）
        self.clean_spin.valueChanged.connect(
            lambda v: (self.clean_slider.blockSignals(True), self.clean_slider.setValue(v), self.clean_slider.blockSignals(False), self._start_preview_timer())
        )
        self.clean_spin.editingFinished.connect(self.refresh_preview)

        settings_layout.addWidget(self.xtc_group)

        # 実行ボタン
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        settings_layout.addWidget(self.progress_bar)

        self.run_btn = QPushButton(_tr("btn_start", self._lang))
        self.run_btn.setObjectName("primaryButton")
        self.run_btn.clicked.connect(self.start_processing)
        settings_layout.addWidget(self.run_btn)

        # 余剰スペースを末尾で吸収（XTC表示切替でグループ1-7の配置が変わらないようにする）
        settings_layout.addStretch()

        # --- ペイン2: リスト (List) ---
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(5, 5, 5, 5)
        
        self._list_group = QGroupBox(_tr("grp_list", self._lang))
        list_vbox = QVBoxLayout(self._list_group)
        sort_layout = QHBoxLayout()
        self._sort_natural_btn = QPushButton(_tr("btn_sort_num", self._lang))
        self._sort_natural_btn.clicked.connect(self.sort_natural)
        sort_layout.addWidget(self._sort_natural_btn)
        self._sort_ascii_btn = QPushButton(_tr("btn_sort_name", self._lang))
        self._sort_ascii_btn.clicked.connect(self.sort_ascii)
        sort_layout.addWidget(self._sort_ascii_btn)
        self._clear_all_btn = QPushButton(_tr("btn_clear", self._lang))
        self._clear_all_btn.clicked.connect(self._clear_all)
        sort_layout.addWidget(self._clear_all_btn)
        list_vbox.addLayout(sort_layout)
        self.image_list_widget = DraggableListWidget()
        self.image_list_widget.itemSelectionChanged.connect(self.on_selection_changed)
        list_vbox.addWidget(self.image_list_widget)
        list_layout.addWidget(self._list_group)

        # --- ペイン3: プレビュー (Preview) ---
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(5, 5, 5, 5)
        
        self._preview_group = QGroupBox(_tr("grp_preview", self._lang))
        preview_vbox = QVBoxLayout(self._preview_group)
        
        # プレビューモード切替ボタン
        mode_toggle_layout = QHBoxLayout()
        self.preprocess_btn = QPushButton(_tr("btn_preprocess", self._lang))
        self.preprocess_btn.setCheckable(True)
        self.preprocess_btn.clicked.connect(lambda: self._set_preview_mode("preprocess"))
        mode_toggle_layout.addWidget(self.preprocess_btn)
        self.output_btn = QPushButton(_tr("btn_output", self._lang))
        self.output_btn.setCheckable(True)
        self.output_btn.setChecked(True)
        self.output_btn.setObjectName("primaryButton")  # デフォルトでハイライト
        self.output_btn.clicked.connect(lambda: self._set_preview_mode("output"))
        mode_toggle_layout.addWidget(self.output_btn)
        preview_vbox.addLayout(mode_toggle_layout)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignCenter)
        
        # 拡張されたプレビューラベル
        self.preview_label = PreviewLabel(self.scroll_area)
        self.preview_label.setText(_tr("lbl_select_image", self._lang))
        self.preview_label.setObjectName("previewLabel")
        self.preview_label.zoomRequested.connect(self.handle_zoom_request)
        self.preview_label.cropRectChanged.connect(self._on_crop_rect_changed)
        self.preview_label.cropDragFinished.connect(self.refresh_preview)
        self.scroll_area.setWidget(self.preview_label)
        preview_vbox.addWidget(self.scroll_area)

        # 分割プレビュー切り替えボタン（トリミング＋分割有効時のみ表示）
        split_toggle_layout = QHBoxLayout()
        self.split_top_btn = QPushButton(_tr("btn_first_page", self._lang))
        self.split_top_btn.setObjectName("splitToggleButton")
        self.split_top_btn.setCheckable(True)
        self.split_top_btn.setChecked(True)
        self.split_top_btn.clicked.connect(lambda: self._set_split_half("first"))
        split_toggle_layout.addWidget(self.split_top_btn)
        self.split_bot_btn = QPushButton(_tr("btn_second_page", self._lang))
        self.split_bot_btn.setObjectName("splitToggleButton")
        self.split_bot_btn.setCheckable(True)
        self.split_bot_btn.clicked.connect(lambda: self._set_split_half("second"))
        split_toggle_layout.addWidget(self.split_bot_btn)
        self.split_toggle_widget = QWidget()
        self.split_toggle_widget.setLayout(split_toggle_layout)
        self.split_toggle_widget.setVisible(False)
        preview_vbox.addWidget(self.split_toggle_widget)

        # プレビュー更新中オーバーレイ（scroll_area のビューポート上に重ねて表示）
        self.loading_overlay = QLabel(_tr("lbl_updating", self._lang), self.scroll_area.viewport())
        self.loading_overlay.setObjectName("loadingOverlay")
        self.loading_overlay.setAlignment(Qt.AlignCenter)
        self.loading_overlay.setVisible(False)
        
        zoom_layout = QHBoxLayout()
        self._zoom_text_label = QLabel(_tr("lbl_zoom", self._lang))
        zoom_layout.addWidget(self._zoom_text_label)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(10, 400)
        self.zoom_slider.setValue(100)
        self.zoom_slider.sliderReleased.connect(self.refresh_preview)
        zoom_layout.addWidget(self.zoom_slider)
        self.zoom_label = QLabel("100%")
        zoom_layout.addWidget(self.zoom_label)
        self.update_label = QLabel("")
        self.update_label.setObjectName("updateIndicator")
        zoom_layout.addWidget(self.update_label)
        preview_vbox.addLayout(zoom_layout)
        
        preview_layout.addWidget(self._preview_group)

        splitter.addWidget(settings_widget)
        splitter.addWidget(list_widget)
        splitter.addWidget(preview_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 2)
        
        main_layout.addWidget(splitter)

    def handle_zoom_request(self, value):
        if value == 0:
            self.zoom_slider.setValue(100)
        else:
            new_val = self.zoom_slider.value() + value
            self.zoom_slider.setValue(max(10, min(400, new_val)))
        self.refresh_preview()

    # --- 言語切替 ---

    def _on_language_changed(self, index: int):
        self._lang = "en" if index == 1 else "ja"
        self._apply_language()

    def _apply_language(self):
        """現在の _lang に基づいて全UIテキストを更新する"""
        lang = self._lang

        # タイトル
        self._title_label.setText(_tr("title_settings", lang))

        # グループボックス
        self._load_group.setTitle(_tr("grp_input", lang))
        self._preproc_group.setTitle(_tr("grp_preprocess", lang))
        self._resize_group.setTitle(_tr("grp_resize", lang))
        self._gray_group.setTitle(_tr("grp_grayscale", lang))
        self._rename_group.setTitle(_tr("grp_rename", lang))
        self.output_name_group.setTitle(_tr("grp_output_name", lang))
        self._format_group.setTitle(_tr("grp_format", lang))
        self.xtc_group.setTitle(_tr("grp_xtc", lang))
        self._list_group.setTitle(_tr("grp_list", lang))
        self._preview_group.setTitle(_tr("grp_preview", lang))

        # チェックボックス
        self.split_check.setText(_tr("chk_auto_split", lang))
        self.auto_rotate_check.setText(_tr("chk_auto_rotate", lang))
        self.trim_check.setText(_tr("chk_auto_trim", lang))
        self.no_resize_check.setText(_tr("chk_no_resize", lang))
        self.gray_check.setText(_tr("chk_enable", lang))
        self.rename_check.setText(_tr("chk_enable", lang))
        self.jpeg_check.setText(_tr("chk_jpeg", lang))
        self.per_folder_check.setText(_tr("chk_per_folder", lang))
        self.edit_name_check.setText(_tr("chk_edit_name", lang))

        # ラベル
        self._preset_label.setText(_tr("lbl_preset", lang))
        self._blur_label.setText(_tr("lbl_blur", lang))
        self.width_label.setText(_tr("lbl_max_w", lang))
        self.height_label.setText(_tr("lbl_max_h", lang))
        self.alignment_label.setText(_tr("lbl_align", lang))
        self.sharpen_label.setText(_tr("lbl_sharpen", lang))
        self.bits_label.setText(_tr("lbl_bits", lang))
        self.dither_algo_label.setText(_tr("lbl_dither_algo", lang))
        self.dither_intensity_label.setText(_tr("lbl_dither_int", lang))
        self.contrast_label.setText(_tr("lbl_contrast", lang))
        self.clahe_label.setText(_tr("lbl_clahe", lang))
        self._prefix_label.setText(_tr("lbl_prefix", lang))
        self._title_label2.setText(_tr("lbl_title", lang))
        self._author_label.setText(_tr("lbl_author", lang))
        self._img_type_label.setText(_tr("lbl_img_type", lang))
        self._dir_label.setText(_tr("lbl_direction", lang))
        self._clean_type_label.setText(_tr("lbl_clean_type", lang))
        self._bg_clean_label.setText(_tr("lbl_bg_clean", lang))
        self._zoom_text_label.setText(_tr("lbl_zoom", lang))

        # ボタン
        self.run_btn.setText(_tr("btn_start", lang))
        self._sort_natural_btn.setText(_tr("btn_sort_num", lang))
        self._sort_ascii_btn.setText(_tr("btn_sort_name", lang))
        self._clear_all_btn.setText(_tr("btn_clear", lang))
        self.preprocess_btn.setText(_tr("btn_preprocess", lang))
        self.output_btn.setText(_tr("btn_output", lang))
        self.split_top_btn.setText(_tr("btn_first_page", lang))
        self.split_bot_btn.setText(_tr("btn_second_page", lang))
        # 分割関連トグルボタンのテキスト更新と最大幅再計算
        self._update_split_btn_widths()
        self._update_split_target_btn_text()
        self._update_split_order_btn_text()

        # コンボボックスアイテム（選択中インデックスを保持して入れ替え）
        def _update_combo(combo, items):
            idx = combo.currentIndex()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(items)
            combo.setCurrentIndex(idx)
            combo.blockSignals(False)

        _update_combo(self.preset_combo, [_tr("combo_preset_none", lang), "Xteink X3 (528×792)", "Xteink X4 (480×800)", "M5Paper S3 (540×960)"])
        _update_combo(self.alignment_combo, [_tr("combo_center", lang), _tr("combo_top", lang)])
        _update_combo(self.output_format_combo, [_tr("combo_individual", lang), "EPUB3", "XTC / XTCH"])
        _update_combo(self.compress_combo, [_tr("combo_folder", lang), "ZIP (.zip)", "CBZ (.cbz)"])
        _update_combo(self.xtc_dir_combo, [_tr("combo_dir_ltr", lang), _tr("combo_dir_rtl", lang), _tr("combo_dir_ttb", lang)])

        # プレースホルダ・ツールチップ
        self.path_edit.setPlaceholderText(_tr("ph_drop", lang))
        self._open_btn.setToolTip(_tr("tip_open", lang))

        # ローディングオーバーレイ
        self.loading_overlay.setText(_tr("lbl_updating", lang))

        # プレビューラベル（画像未選択時のみ更新）
        if self.current_preview_image is None:
            self.preview_label.setText(_tr("lbl_select_image", lang))

        # パス表示を再更新
        self._update_path_display()

        # 出力名プレビューを再更新
        self._update_output_name_preview()

    # --- 余白トリミング関連 ---

    def _on_split_changed(self):
        is_split = self.split_check.isChecked()
        self.split_toggle_widget.setVisible(is_split)
        # 自動分割OFF時は分割関連トグルボタンを無効化
        self.split_target_btn.setEnabled(is_split)
        self.split_order_btn.setEnabled(is_split)
        if not is_split:
            self._split_preview_half = "first"
            self.split_top_btn.setChecked(True)
            self.split_bot_btn.setChecked(False)
        self.crop_rects.clear()
        if self.trim_check.isChecked():
            self._start_trim_detection()
        self.refresh_preview()

    def _update_split_btn_widths(self):
        """分割関連トグルボタンを「全状態テキストの最大幅」で固定する。
        言語切替や初期化時に呼び出し、テキスト変動による幅の揺れを抑える。"""
        # 適用対象（3状態）
        target_texts = [_tr(k, self._lang) for k in
                        ("btn_split_target_both", "btn_split_target_lr", "btn_split_target_tb")]
        fm = self.split_target_btn.fontMetrics()
        # padding(2+6+6+2≈16) + 余裕(8) を加算
        target_w = max(fm.horizontalAdvance(t) for t in target_texts) + 24
        self.split_target_btn.setFixedWidth(target_w)
        # 順序（2状態）
        order_texts = [_tr(k, self._lang) for k in ("btn_split_order_lr", "btn_split_order_rl")]
        order_w = max(fm.horizontalAdvance(t) for t in order_texts) + 24
        self.split_order_btn.setFixedWidth(order_w)

    def _update_split_target_btn_text(self):
        keys = ["btn_split_target_both", "btn_split_target_lr", "btn_split_target_tb"]
        self.split_target_btn.setText(_tr(keys[self._split_target], self._lang))

    def _update_split_order_btn_text(self):
        key = "btn_split_order_lr" if self._split_order_h == 0 else "btn_split_order_rl"
        self.split_order_btn.setText(_tr(key, self._lang))

    def _on_split_target_toggle(self):
        # 0=両方 → 1=左右のみ → 2=上下のみ → 0 のサイクル
        self._split_target = (self._split_target + 1) % 3
        self._update_split_target_btn_text()
        # crop_rects は保持し、ユーザーが手動調整したクロップ矩形が失われないようにする。
        # 設定変更で意味が変わるキー（例: split_target=1で縦長画像のtop/bot）は参照されなくなるが、
        # 再度該当設定に戻った際に復元できるためメモリ上で保持する。不足分は on-demand 検出で補う。
        if self.trim_check.isChecked() and self.split_check.isChecked():
            # 既存の crop_rects は保持しつつ、新たな suffix が必要な分だけ検出を再実行
            self._start_trim_detection(clear_existing=False)
        self.refresh_preview()

    def _on_split_order_toggle(self):
        # 0=左→右 ⇄ 1=右→左
        self._split_order_h = 1 - self._split_order_h
        self._update_split_order_btn_text()
        # クロップ矩形のキー（left/right）はそのまま、プレビューの再描画のみで対応
        self.refresh_preview()

    def _on_trim_changed(self):
        self.split_toggle_widget.setVisible(self.split_check.isChecked())
        if self.trim_check.isChecked():
            self._start_trim_detection()
        else:
            self._stop_trim_detection()
        self.refresh_preview()

    def _set_split_half(self, half: str):
        self._split_preview_half = half
        self.split_top_btn.setChecked(half == "first")
        self.split_bot_btn.setChecked(half == "second")
        self.refresh_preview()

    def _set_preview_mode(self, mode: str):
        self._preview_mode = mode
        self.preprocess_btn.setChecked(mode == "preprocess")
        self.output_btn.setChecked(mode == "output")
        # 選択中ボタンを primaryButton スタイルでハイライト
        self.preprocess_btn.setObjectName("primaryButton" if mode == "preprocess" else "")
        self.output_btn.setObjectName("primaryButton" if mode == "output" else "")
        self.preprocess_btn.style().unpolish(self.preprocess_btn)
        self.preprocess_btn.style().polish(self.preprocess_btn)
        self.output_btn.style().unpolish(self.output_btn)
        self.output_btn.style().polish(self.output_btn)
        self.refresh_preview()

    def _on_crop_rect_changed(self, rect: tuple):
        """クロップ枠ドラッグ中 — 生画像座標系で直接格納"""
        if self._current_crop_key is not None:
            self.crop_rects[self._current_crop_key] = rect

    def _start_trim_detection(self, clear_existing: bool = True):
        self._stop_trim_detection()
        if not self.trim_check.isChecked() or self.image_list_widget.count() == 0:
            return
        if clear_existing:
            self.crop_rects.clear()
        abs_paths = [self.image_list_widget.item(i).data(Qt.UserRole)
                     for i in range(self.image_list_widget.count())]
        self._trim_detect_thread = TrimDetectThread(
            abs_paths, self.split_check.isChecked(), self._split_target
        )
        self._trim_detect_thread.detected.connect(self._on_trim_detected)
        self._trim_detect_thread.all_done.connect(self._on_trim_all_done)
        self._trim_detect_thread.start()

    def _stop_trim_detection(self):
        if self._trim_detect_thread is not None:
            self._trim_detect_thread.abort()
            if not self._trim_detect_thread.wait(3000):
                self._trim_detect_thread.terminate()
            self._trim_detect_thread.deleteLater()
            self._trim_detect_thread = None

    def _on_trim_detected(self, abs_path: str, suffix: str, rect: tuple):
        key = (abs_path, suffix)
        # ユーザーが手動調整済みの場合は上書きしない
        if key not in self.crop_rects:
            self.crop_rects[key] = rect
        # 現在プレビュー中の画像であればプレビュー更新
        if self._current_crop_key == key:
            self.refresh_preview()

    def _on_trim_all_done(self):
        pass

    def _build_crop_rects_for_batch(self, current_images):
        """バッチ処理用のcrop_rectsを返す（キーは絶対パス）"""
        if not self.trim_check.isChecked() or not self.crop_rects:
            return None
        return dict(self.crop_rects)

    def _natural_sort_key(self, text):
        return [int(p) if p.isdigit() else p.lower() for p in re.split(r'(\d+)', text)]

    def _sort_list_widget(self, key_func):
        items_data = []
        for i in range(self.image_list_widget.count()):
            item = self.image_list_widget.item(i)
            items_data.append((item.text(), item.data(Qt.UserRole),
                               item.data(Qt.UserRole + 1), item.data(Qt.UserRole + 2),
                               item.data(Qt.UserRole + 3)))
        if not items_data:
            return
        # ソースラベル単位でグルーピングを保つため、(ソースラベル, ファイル名) の複合キーでソート
        items_data.sort(key=lambda x: (key_func(x[2] or ""), key_func(x[3] or x[0])))
        self.image_list_widget.clear()
        for text, data, src_label, rel_disp, src_id in items_data:
            new_item = QListWidgetItem(text)
            new_item.setData(Qt.UserRole, data)
            new_item.setData(Qt.UserRole + 1, src_label)
            new_item.setData(Qt.UserRole + 2, rel_disp)
            new_item.setData(Qt.UserRole + 3, src_id)
            self.image_list_widget.addItem(new_item)

    def sort_natural(self):
        self._sort_list_widget(self._natural_sort_key)

    def sort_ascii(self):
        self._sort_list_widget(lambda x: x)

    def on_gray_changed(self, checked):
        # XTC選択時は常にグレースケール有効なのでサブ設定も有効のまま
        is_xtc = self.output_format_combo.currentIndex() == 2
        enabled = checked or is_xtc
        for w in [self.bits_label, self.bits_spin,
                  self.dither_algo_label, self.dither_algo_combo,
                  self.dither_intensity_label, self.dither_slider, self.dither_spin,
                  self.contrast_label, self.contrast_slider, self.contrast_spin,
                  self.clahe_label, self.clahe_slider, self.clahe_spin]:
            w.setEnabled(enabled)
        self.refresh_preview()

    def _start_preview_timer(self):
        """デバウンスタイマーを起動し、更新中インジケータを表示する"""
        self.update_label.setText(_tr("lbl_updating_short", self._lang))
        self._preview_timer.start()

    def on_format_changed(self, index):
        # 0: 個別, 1: EPUB, 2: XTC
        is_individual = index == 0
        is_xtc  = index == 2
        # グループ8: XTC詳細設定 → XTC時のみ表示
        self.xtc_group.setVisible(is_xtc)
        # JPEG強制チェック・圧縮オプションは個別画像時のみ
        self.jpeg_check.setVisible(is_individual)
        self.compress_combo.setVisible(is_individual)
        # XTC選択時はグレースケールを強制ON・無効化
        if is_xtc:
            self.gray_check.setChecked(True)
            self.gray_check.setEnabled(False)
        else:
            self.gray_check.setEnabled(True)
        self._update_output_name_preview()
        self.refresh_preview()

    def on_edit_name_changed(self, checked):
        """「編集する」チェックボックスの状態に応じてタイトル・著者欄を有効/無効化"""
        self.epub_title_edit.setEnabled(checked)
        self.epub_author_edit.setEnabled(checked)
        self._title_label2.setEnabled(checked)
        self._author_label.setEnabled(checked)
        self._update_output_name_preview()

    def _first_source_label(self) -> str:
        """画像一覧の先頭アイテムのソースラベルを返す（空なら "")"""
        if self.image_list_widget.count() == 0:
            return ""
        return self.image_list_widget.item(0).data(Qt.UserRole + 1) or ""

    def _build_output_base(self) -> str:
        """編集モード/ソースラベルに応じた出力名のベースを返す"""
        if self.edit_name_check.isChecked():
            title = self.epub_title_edit.text().strip()
            author = self.epub_author_edit.text().strip()
            if author and title:
                return f"[{author}] {title}"
            if title:
                return title
            if author:
                return f"[{author}]"
            return ""
        # 編集無効時は最初のソースラベルをベースとする
        return self._first_source_label()

    def _update_output_name_preview(self):
        """出力ファイル/フォルダ名をプレビュー表示する"""
        base = self._build_output_base()
        if not base:
            self.output_name_preview.setText("")
            return

        format_idx = self.output_format_combo.currentIndex()
        if format_idx == 0:
            # 個別画像
            compress_idx = self.compress_combo.currentIndex()
            if compress_idx == 1:
                name = f"{base}.zip"
            elif compress_idx == 2:
                name = f"{base}.cbz"
            else:
                name = f"{base}/"
        elif format_idx == 1:
            name = f"{base}.epub"
        elif format_idx == 2:
            ext = "xtch" if self.xtc_bit_combo.currentIndex() == 1 else "xtc"
            name = f"{base}.{ext}"
        else:
            name = base

        self.output_name_preview.setText(f"→ {name}")

    def on_no_resize_changed(self, checked):
        no_resize = checked
        preset_active = self.preset_combo.currentIndex() != 0
        # リサイズなし時は関連設定を無効化
        self._preset_label.setEnabled(not no_resize)
        self.preset_combo.setEnabled(not no_resize)
        self.width_spin.setEnabled(not no_resize and not preset_active)
        self.height_spin.setEnabled(not no_resize and not preset_active)
        self.width_label.setEnabled(not no_resize)
        self.height_label.setEnabled(not no_resize)
        self.alignment_label.setEnabled(not no_resize)
        self.alignment_combo.setEnabled(not no_resize)
        self.sharpen_label.setEnabled(not no_resize)
        self.sharpen_slider.setEnabled(not no_resize)
        self.sharpen_spin.setEnabled(not no_resize)
        self.auto_rotate_check.setEnabled(not no_resize)
        # リサイズ有無で出力画像サイズが大きく変わるため、ズームを100%にリセット
        self.zoom_slider.setValue(100)
        self.refresh_preview()

    def on_preset_changed(self, index):
        no_resize = self.no_resize_check.isChecked()
        preset_active = index != 0
        self.width_spin.setEnabled(not preset_active and not no_resize)
        self.height_spin.setEnabled(not preset_active and not no_resize)
        self.width_label.setEnabled(not no_resize)
        self.height_label.setEnabled(not no_resize)
        _PRESET_SIZES = {1: (528, 792), 2: (480, 800), 3: (540, 960)}
        if index in _PRESET_SIZES:
            w, h = _PRESET_SIZES[index]
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)
        self.refresh_preview()

    def load_stylesheet(self):
        # PyInstaller / Nuitka / 開発環境 共通のアセットパス解決
        if hasattr(sys, '_MEIPASS'):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))

        qss_path = os.path.join(base_path, "style.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                content = f.read()
            # QSS内の相対URLをPyInstaller環境でも解決できるよう絶対パスに変換する
            # Qt はパス区切りにスラッシュを使う。スペースを含むパスに対応するため引用符でラップする
            asset_path = base_path.replace("\\", "/")
            for svg_file in ("arrow_up.svg", "arrow_down.svg"):
                content = content.replace(f"url({svg_file})", f'url("{asset_path}/{svg_file}")')
            self.setStyleSheet(content)

    def save_settings(self):
        s = QSettings("antigravity", "XteinkImageRefiner")
        s.setValue("no_resize",         self.no_resize_check.isChecked())
        s.setValue("width",            self.width_spin.value())
        s.setValue("height",           self.height_spin.value())
        s.setValue("preset_index",     self.preset_combo.currentIndex())
        s.setValue("alignment",        self.alignment_combo.currentIndex())
        s.setValue("sharpen",          self.sharpen_slider.value())
        s.setValue("split",            self.split_check.isChecked())
        s.setValue("split_target",     self._split_target)
        s.setValue("split_order_h",    self._split_order_h)
        s.setValue("auto_rotate",      self.auto_rotate_check.isChecked())
        s.setValue("grayscale",        self.gray_check.isChecked())
        s.setValue("bits",             self.bits_spin.value())
        s.setValue("dither_algo",      self.dither_algo_combo.currentIndex())
        s.setValue("dither_intensity", self.dither_slider.value())
        s.setValue("rename",           self.rename_check.isChecked())
        s.setValue("prefix",           self.prefix_edit.text())
        s.setValue("output_format",    self.output_format_combo.currentIndex())
        s.setValue("force_jpeg",       self.jpeg_check.isChecked())
        s.setValue("compress_format",  self.compress_combo.currentIndex())
        s.setValue("per_folder",       self.per_folder_check.isChecked())
        s.setValue("edit_name",        self.edit_name_check.isChecked())
        s.setValue("xtc_bit",          self.xtc_bit_combo.currentIndex())
        s.setValue("xtc_dir",          self.xtc_dir_combo.currentIndex())
        s.setValue("clean_algo",       self.clean_algo_combo.currentIndex())
        s.setValue("clean_intensity",  self.clean_slider.value())
        s.setValue("blur_strength",    self.blur_slider.value())
        s.setValue("contrast",         self.contrast_slider.value())
        s.setValue("clahe",            self.clahe_slider.value())
        s.setValue("trim_enabled",     self.trim_check.isChecked())
        s.setValue("preview_mode",     self._preview_mode)
        s.setValue("language",         self._lang)

    def load_settings(self):
        s = QSettings("antigravity", "XteinkImageRefiner")
        # no_resize → 幅・高さ → プリセット の順で読む（依存関係のため）
        self.no_resize_check.setChecked(   s.value("no_resize",        False, type=bool))
        self.width_spin.setValue(          s.value("width",            1920, type=int))
        self.height_spin.setValue(         s.value("height",           1080, type=int))
        # 旧設定 (x4_preset=True) からの移行: preset_index が未設定なら x4_preset を参照
        preset_idx = s.value("preset_index", -1, type=int)
        if preset_idx < 0:
            preset_idx = 2 if s.value("x4_preset", False, type=bool) else 0
        self.preset_combo.setCurrentIndex(preset_idx)
        self.alignment_combo.setCurrentIndex(s.value("alignment",       0,    type=int))
        self.sharpen_slider.setValue(      s.value("sharpen",          0,    type=int))
        self.split_check.setChecked(       s.value("split",            False, type=bool))
        # 自動分割の適用対象・順序の復元
        self._split_target = max(0, min(2, s.value("split_target",    0, type=int)))
        self._split_order_h = max(0, min(1, s.value("split_order_h",  0, type=int)))
        self._update_split_target_btn_text()
        self._update_split_order_btn_text()
        # split_check の現在値に応じてトグルボタンの有効/無効を反映
        self.split_target_btn.setEnabled(self.split_check.isChecked())
        self.split_order_btn.setEnabled(self.split_check.isChecked())
        self.auto_rotate_check.setChecked( s.value("auto_rotate",      False, type=bool))
        self.blur_slider.setValue(         s.value("blur_strength",     0,    type=int))
        self.gray_check.setChecked(        s.value("grayscale",        False, type=bool))
        self.bits_spin.setValue(           s.value("bits",             8,    type=int))
        self.dither_algo_combo.setCurrentIndex(s.value("dither_algo",  0,    type=int))
        self.dither_slider.setValue(       s.value("dither_intensity",  0,    type=int))
        self.contrast_slider.setValue(     s.value("contrast",          0,    type=int))
        self.clahe_slider.setValue(       s.value("clahe",             0,    type=int))
        self.rename_check.setChecked(      s.value("rename",           True,  type=bool))
        self.prefix_edit.setText(          s.value("prefix",           "image"))
        self.output_format_combo.setCurrentIndex(s.value("output_format", 0,  type=int))
        self.jpeg_check.setChecked(        s.value("force_jpeg",       False, type=bool))
        self.compress_combo.setCurrentIndex(s.value("compress_format", 0,    type=int))
        self.per_folder_check.setChecked(  s.value("per_folder",        False, type=bool))
        # blockSignals で toggled シグナル発火を抑制し、後で1回だけ on_edit_name_changed を呼ぶ
        self.edit_name_check.blockSignals(True)
        self.edit_name_check.setChecked(   s.value("edit_name",         True,  type=bool))
        self.edit_name_check.blockSignals(False)
        self.on_edit_name_changed(self.edit_name_check.isChecked())
        self.xtc_bit_combo.setCurrentIndex(s.value("xtc_bit",          0,    type=int))
        self.xtc_dir_combo.setCurrentIndex(s.value("xtc_dir",          1,    type=int))
        self.clean_algo_combo.setCurrentIndex(s.value("clean_algo",    0,    type=int))
        self.clean_slider.setValue(        s.value("clean_intensity",  0,    type=int))
        self.trim_check.setChecked(        s.value("trim_enabled",     False, type=bool))
        self._set_preview_mode(       s.value("preview_mode",     "output", type=str))
        # 言語設定の復元
        saved_lang = s.value("language", "ja", type=str)
        if saved_lang in ("ja", "en"):
            self._lang = saved_lang
            self._lang_combo.blockSignals(True)
            self._lang_combo.setCurrentIndex(1 if saved_lang == "en" else 0)
            self._lang_combo.blockSignals(False)
            self._apply_language()

    def _allocate_source_id(self) -> int:
        """新しいソースIDを発行する。同名フォルダ衝突時のグループ識別に使用。"""
        sid = self._next_source_id
        self._next_source_id += 1
        return sid

    def _clear_temp_dirs(self):
        for d in self._temp_dirs:
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
        self._temp_dirs.clear()

    def _clear_all(self):
        """全データをクリアして起動直後の状態に戻す"""
        self._stop_trim_detection()
        self.image_list_widget.clear()
        self.crop_rects.clear()
        self._next_source_id = 0
        self._current_crop_key = None
        self._current_raw_preview = None
        self._release_preview_image()
        self._clear_temp_dirs()
        self.path_edit.setText("")
        self.epub_title_edit.setText("")
        self.epub_author_edit.setText("")
        self.preview_label.clear()
        self.preview_label.clear_crop_mode()
        self.preview_label.adjustSize()

    def closeEvent(self, event):
        self._stop_trim_detection()
        self.save_settings()
        self._clear_temp_dirs()
        super().closeEvent(event)

    # --- ドラッグ＆ドロップ実装 ---
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if not urls:
            return
        image_files = []
        for url in urls:
            path = url.toLocalFile()
            if os.path.isdir(path):
                self.handle_folder_load(path)
            elif path.lower().endswith(".zip"):
                self.handle_zip_load(path)
            elif path.lower().endswith(self._VALID_IMAGE_EXTS):
                image_files.append(path)
        if image_files:
            self._add_image_files(image_files)
            self._update_path_display()

    def select_input(self):
        # フォルダ、ZIP、画像ファイルを複数選択可能なダイアログ
        dialog = QFileDialog(self, _tr("dlg_select_input", self._lang))
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilters([
            _tr("dlg_filter_images", self._lang),
            _tr("dlg_filter_all", self._lang)
        ])
        if dialog.exec():
            selected = dialog.selectedFiles()
            image_files = []
            for path in selected:
                if os.path.isdir(path):
                    self.handle_folder_load(path)
                elif path.lower().endswith(".zip"):
                    self.handle_zip_load(path)
                elif path.lower().endswith(self._VALID_IMAGE_EXTS):
                    image_files.append(path)
            if image_files:
                self._add_image_files(image_files)
                self._update_path_display()

    def _release_preview_image(self):
        """プレビュー画像のファイルハンドルを解放する"""
        if self.current_preview_image is not None:
            self.current_preview_image.close()
            self.current_preview_image = None

    def handle_folder_load(self, path):
        # 画像一覧が空の場合のみメタデータを取得（最初にドロップしたソースから取得）
        if self.image_list_widget.count() == 0:
            self.extract_metadata_from_name(os.path.basename(path))
        self._add_images_from_folder(path, os.path.basename(path), self._allocate_source_id())
        self._update_path_display()

    def handle_zip_load(self, path):
        try:
            name = os.path.basename(path)
            if name.lower().endswith(".zip"):
                name = name[:-4]
            if self.image_list_widget.count() == 0:
                self.extract_metadata_from_name(name)

            temp_dir = tempfile.mkdtemp(prefix="img_editor_")
            with zipfile.ZipFile(path, 'r') as zip_ref:
                # ZIPスリップ対策: パストラバーサルを検出して拒否
                real_temp = os.path.realpath(temp_dir)
                for info in zip_ref.infolist():
                    target = os.path.realpath(os.path.join(temp_dir, info.filename))
                    if not target.startswith(real_temp + os.sep) and target != real_temp:
                        raise ValueError(f"不正なパスを含むZIP: {info.filename}")
                zip_ref.extractall(temp_dir)
            self._temp_dirs.append(temp_dir)
            self._add_images_from_folder(temp_dir, name, self._allocate_source_id())
            self._update_path_display()
        except Exception as e:
            QMessageBox.critical(self, _tr("dlg_error", self._lang), _tr("msg_zip_fail", self._lang, e=e))

    def _update_path_display(self):
        """ソース数に応じてパス表示を更新する"""
        sources = set()
        for i in range(self.image_list_widget.count()):
            sources.add(self.image_list_widget.item(i).data(Qt.UserRole + 1))
        # 編集無効時はソースラベルが出力名に使われるため、プレビューも更新する
        if not self.edit_name_check.isChecked():
            self._update_output_name_preview()
        if len(sources) == 0:
            self.path_edit.setText("")
        elif len(sources) == 1:
            self.path_edit.setText(next(iter(sources)))
        else:
            self.path_edit.setText(_tr("msg_sources", self._lang, n=len(sources)))

    def extract_metadata_from_name(self, name):
        # [著者]タイトル 形式の抽出
        match = re.match(r'^\[(.*?)\]\s*(.*)$', name)
        if match:
            self.epub_author_edit.setText(match.group(1).strip())
            self.epub_title_edit.setText(match.group(2).strip())
        else:
            self.epub_author_edit.setText("")
            self.epub_title_edit.setText(name)

    _VALID_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")

    def _add_images_from_folder(self, folder: str, source_label: str, source_id: int):
        """フォルダ内の画像をリストに追加する（既存アイテムはクリアしない）"""
        was_empty = self.image_list_widget.count() == 0
        try:
            files: list[tuple[str, str]] = []  # (abs_path, rel_display)
            for root, dirs, filenames in os.walk(folder):
                for f in filenames:
                    if f.lower().endswith(self._VALID_IMAGE_EXTS):
                        abs_path = os.path.join(root, f)
                        rel_path = os.path.relpath(abs_path, folder)
                        files.append((abs_path, rel_path))

            files.sort(key=lambda x: x[1])

            # 同一ソース内のサブフォルダ判定
            dirs_in_source = set(os.path.dirname(r) for _, r in files)
            multi_sub = len(dirs_in_source) > 1
            for abs_path, rel_path in files:
                rel_display = rel_path if multi_sub else os.path.basename(rel_path)
                item = QListWidgetItem(rel_display)
                item.setData(Qt.UserRole, abs_path)
                item.setData(Qt.UserRole + 1, source_label)
                item.setData(Qt.UserRole + 2, rel_display)
                item.setData(Qt.UserRole + 3, source_id)
                self.image_list_widget.addItem(item)

            # リストが空だった場合のみ、1枚目の解像度を初期値にセット
            if was_empty and files and self.preset_combo.currentIndex() == 0:
                first_path = files[0][0]
                with Image.open(first_path) as img:
                    w, h = img.size
                self.width_spin.blockSignals(True)
                self.height_spin.blockSignals(True)
                self.width_spin.setValue(w)
                self.height_spin.setValue(h)
                self.width_spin.blockSignals(False)
                self.height_spin.blockSignals(False)

            self._refresh_display_names()

            # トリミング有効時は余白一括検出を起動（既存の検出結果はクリアしない）
            if self.trim_check.isChecked() and files:
                self._start_trim_detection(clear_existing=False)
        except Exception as e:
            QMessageBox.critical(self, _tr("dlg_error", self._lang), _tr("msg_load_fail", self._lang, e=e))

    def _add_image_files(self, file_paths: list[str]):
        """個別の画像ファイルをリストに追加する。親フォルダ単位で source_id を割り当てる。"""
        was_empty = self.image_list_widget.count() == 0
        added = []
        parent_to_id: dict[str, int] = {}  # 絶対パスの親ディレクトリ -> source_id
        for path in file_paths:
            if not path.lower().endswith(self._VALID_IMAGE_EXTS):
                continue
            abs_path = os.path.abspath(path)
            parent_dir = os.path.dirname(abs_path)
            if parent_dir not in parent_to_id:
                parent_to_id[parent_dir] = self._allocate_source_id()
            source_id = parent_to_id[parent_dir]
            source_label = os.path.basename(parent_dir)
            rel_display = os.path.basename(abs_path)
            item = QListWidgetItem(rel_display)
            item.setData(Qt.UserRole, abs_path)
            item.setData(Qt.UserRole + 1, source_label)
            item.setData(Qt.UserRole + 2, rel_display)
            item.setData(Qt.UserRole + 3, source_id)
            self.image_list_widget.addItem(item)
            added.append(abs_path)

        if not added:
            return

        # リストが空だった場合のみ、1枚目の解像度を初期値にセット
        if was_empty and self.preset_combo.currentIndex() == 0:
            try:
                with Image.open(added[0]) as img:
                    w, h = img.size
                self.width_spin.blockSignals(True)
                self.height_spin.blockSignals(True)
                self.width_spin.setValue(w)
                self.height_spin.setValue(h)
                self.width_spin.blockSignals(False)
                self.height_spin.blockSignals(False)
            except Exception:
                pass

        self._refresh_display_names()

        if self.trim_check.isChecked():
            self._start_trim_detection(clear_existing=False)

    def _refresh_display_names(self):
        """ソース数に応じてリスト表示名を更新する"""
        count = self.image_list_widget.count()
        if count == 0:
            return
        sources = set()
        for i in range(count):
            sources.add(self.image_list_widget.item(i).data(Qt.UserRole + 1))
        multi_source = len(sources) > 1
        self.image_list_widget.blockSignals(True)
        for i in range(count):
            item = self.image_list_widget.item(i)
            rel_display = item.data(Qt.UserRole + 2)
            if multi_source:
                source_label = item.data(Qt.UserRole + 1)
                item.setText(f"{source_label}/{rel_display}")
            else:
                item.setText(rel_display)
        self.image_list_widget.blockSignals(False)

    def on_selection_changed(self):
        selected_items = self.image_list_widget.selectedItems()
        if not selected_items:
            return

        full_path = selected_items[0].data(Qt.UserRole)

        # 前の画像を解放してからロード（ファイルハンドルリーク防止）
        if self.current_preview_image is not None:
            self.current_preview_image.close()
            self.current_preview_image = None

        try:
            with Image.open(full_path) as img:
                img.load()
                self.current_preview_image = img.copy()
            self.refresh_preview()
        except Exception as e:
            self.preview_label.setText(_tr("msg_preview_fail", self._lang, e=e))
            self.current_preview_image = None

    def refresh_preview(self):
        if self.current_preview_image is None or self._preview_running:
            return
        self._preview_running = True

        # viewport 全体を覆うオーバーレイを表示
        vp = self.scroll_area.viewport()
        self.loading_overlay.setGeometry(vp.rect())
        self.loading_overlay.setVisible(True)
        self.loading_overlay.raise_()
        # repaint() で同期的にフレームバッファへ書き込む
        # （paint イベントはタイマーより低優先度のため、singleShot の前に必須）
        self.loading_overlay.repaint()

        # 次のイベントループで処理開始（repaint 済みなので DWM が次 vsync で表示する）
        QTimer.singleShot(0, self._execute_preview)

    def _execute_preview(self):
        """オーバーレイ表示後、次イベントループで実行されるプレビュー処理"""
        try:
            if self.current_preview_image:
                self._do_refresh_preview()
        finally:
            self.loading_overlay.setVisible(False)
            self.update_label.setText("")
            self._preview_running = False

    def _do_refresh_preview(self):
        # 0. 前処理: 自動分割
        from image_processor import split_image_top_bottom, split_image_left_right
        preview_src = self.current_preview_image.copy()

        selected_items = self.image_list_widget.selectedItems()
        abs_path = selected_items[0].data(Qt.UserRole) if selected_items else ""

        if self.split_check.isChecked():
            w, h = preview_src.size
            is_landscape = (w >= h)
            apply_split = (
                self._split_target == 0  # 両方
                or (self._split_target == 1 and is_landscape)   # 左右のみ
                or (self._split_target == 2 and not is_landscape)  # 上下のみ
            )
            # 分割が実際に適用されるかどうかでプレビュー切替ボタンの有効/無効を制御
            self.split_top_btn.setEnabled(apply_split)
            self.split_bot_btn.setEnabled(apply_split)
            # 分割対象画像のときは _split_preview_half の現在値をボタンの選択状態に反映
            # （分割対象外の画像を経由しても、戻った時に正しいハイライトが復元される）
            if apply_split:
                self.split_top_btn.setChecked(self._split_preview_half == "first")
                self.split_bot_btn.setChecked(self._split_preview_half == "second")
            if apply_split and is_landscape:
                # 横長 → 左右分割。順序設定により1番目を切替
                left_img, right_img = split_image_left_right(preview_src)
                first_is_right = (self._split_order_h == 1)
                first_img, first_suf = (right_img, "right") if first_is_right else (left_img, "left")
                second_img, second_suf = (left_img, "left") if first_is_right else (right_img, "right")
                if self._split_preview_half == "second":
                    preview_src, suffix = second_img, second_suf
                else:
                    preview_src, suffix = first_img, first_suf
            elif apply_split and not is_landscape:
                # 縦長 → 上下分割。順序は上→下固定
                top_img, bot_img = split_image_top_bottom(preview_src)
                preview_src = bot_img if self._split_preview_half == "second" else top_img
                suffix = "bot" if self._split_preview_half == "second" else "top"
            else:
                # 分割対象外: ボタンは disabled になるのでチェック状態は変更しない
                # （_split_preview_half を維持し、再度分割対象画像に戻った際に復元）
                suffix = ""
        else:
            suffix = ""

        # クロップキーと生画像の保存
        self._current_crop_key = (abs_path, suffix)
        self._current_raw_preview = preview_src.copy()
        raw_w, raw_h = preview_src.size

        # トリミング有効時: クロップ矩形を取得（on-demand検出含む）
        trim_active = self.trim_check.isChecked()
        crop_rect = None
        if trim_active:
            key = self._current_crop_key
            if key not in self.crop_rects:
                from image_processor import detect_trim_rect
                self.crop_rects[key] = detect_trim_rect(preview_src)
            crop_rect = self.crop_rects[key]

        zoom = self.zoom_slider.value() / 100.0
        self.zoom_label.setText(f"{int(zoom * 100)}%")

        if self._preview_mode == "preprocess":
            # ── 前処理プレビュー: 生画像 + クロップ枠 ──
            display = preview_src
            if display.mode not in ("RGB", "L"):
                display = display.convert("RGB")

            if display.mode == "L":
                img_format = QImage.Format_Grayscale8
                bpl = display.width
            else:
                img_format = QImage.Format_RGB888
                bpl = display.width * 3

            data = display.tobytes("raw", display.mode)
            qimg = QImage(data, display.width, display.height, bpl, img_format)
            pixmap = QPixmap.fromImage(qimg)

            if zoom != 1.0:
                new_size = pixmap.size() * zoom
                pixmap = pixmap.scaled(new_size, Qt.KeepAspectRatio,
                                       Qt.FastTransformation if zoom > 1.0 else Qt.SmoothTransformation)

            self.preview_label.setPixmap(pixmap)
            self.preview_label.adjustSize()

            if trim_active and crop_rect is not None:
                self.preview_label.set_crop_params(crop_rect, (raw_w, raw_h), zoom)
            else:
                self.preview_label.clear_crop_mode()
        else:
            # ── 出力プレビュー: フル処理パイプライン ──
            cropped = preview_src.crop(crop_rect) if (trim_active and crop_rect) else preview_src

            processed_pil = apply_processing(
                cropped,
                self.width_spin.value(),
                self.height_spin.value(),
                self.gray_check.isChecked(),
                self.bits_spin.value(),
                alignment="top" if self.alignment_combo.currentIndex() == 1 else "center",
                blur_strength=self.blur_slider.value(),
                contrast=self.contrast_slider.value(),
                auto_rotate=self.auto_rotate_check.isChecked(),
                sharpen=self.sharpen_slider.value(),
                clahe=self.clahe_slider.value(),
                no_resize=self.no_resize_check.isChecked()
            )

            is_xtc = self.output_format_combo.currentIndex() == 2
            use_gray = self.gray_check.isChecked()

            target_bits = 8
            if is_xtc:
                target_bits = 1 if self.xtc_bit_combo.currentIndex() == 0 else 2

            dither_algo = self.dither_algo_combo.currentText()
            dither_intensity = self.dither_slider.value()

            if use_gray or is_xtc:
                processed_pil = apply_bit_dithering(processed_pil, target_bits, dither_intensity, dither_algo)

            clean_val = self.clean_slider.value()
            if clean_val > 0:
                clean_algo = self.clean_algo_combo.currentText()
                processed_pil = apply_cv2_cleaning(processed_pil, clean_val, clean_algo)

            if is_xtc:
                if target_bits == 2:
                    def map_sim(p):
                        if p > 191: return 255
                        if p > 127: return 180
                        if p > 63:  return 90
                        return 0
                    processed_pil = processed_pil.point(map_sim)
                elif target_bits == 1:
                    processed_pil = processed_pil.convert("L")

            if processed_pil.mode == "L":
                img_format = QImage.Format_Grayscale8
                bytes_per_line = processed_pil.width
            else:
                img_format = QImage.Format_RGB888
                processed_pil = processed_pil.convert("RGB")
                bytes_per_line = processed_pil.width * 3

            data = processed_pil.tobytes("raw", processed_pil.mode)
            qimg = QImage(data, processed_pil.width, processed_pil.height, bytes_per_line, img_format)
            pixmap = QPixmap.fromImage(qimg)

            if zoom != 1.0:
                new_size = pixmap.size() * zoom
                pixmap = pixmap.scaled(new_size, Qt.KeepAspectRatio,
                                       Qt.FastTransformation if zoom > 1.0 else Qt.SmoothTransformation)

            self.preview_label.setPixmap(pixmap)
            self.preview_label.adjustSize()
            self.preview_label.clear_crop_mode()

    def start_processing(self):
        if self.image_list_widget.count() == 0:
            QMessageBox.warning(self, _tr("dlg_error", self._lang), _tr("msg_no_images", self._lang))
            return

        output_dir = QFileDialog.getExistingDirectory(self, _tr("dlg_select_output", self._lang))
        if not output_dir:
            return

        current_images = []
        current_source_labels = []
        current_source_ids = []
        for i in range(self.image_list_widget.count()):
            item = self.image_list_widget.item(i)
            current_images.append(item.data(Qt.UserRole))
            current_source_labels.append(item.data(Qt.UserRole + 1))
            current_source_ids.append(item.data(Qt.UserRole + 3))

        self.run_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)

        format_idx = self.output_format_combo.currentIndex()

        # 出力名の構築
        # 編集モード ON: [著者] タイトル 形式
        # 編集モード OFF + per_folder OFF: 最初のソースラベル
        # 編集モード OFF + per_folder ON: ProcessingThread 側で各グループのラベルを使用
        title = self.epub_title_edit.text().strip()
        author = self.epub_author_edit.text().strip()
        edit_name_enabled = self.edit_name_check.isChecked()
        per_folder_enabled = self.per_folder_check.isChecked()
        use_source_label_per_group = (not edit_name_enabled) and per_folder_enabled

        if edit_name_enabled:
            if author and title:
                output_name = f"[{author}] {title}"
            elif title:
                output_name = title
            else:
                output_name = ""
        else:
            # 編集無効: 最初のソースラベルを使う（per_folder時は ProcessingThread で上書きされる）
            output_name = current_source_labels[0] if current_source_labels else ""
        # ファイル名として無効な文字をサニタイズ（出力名が空の場合はそのまま空とする）
        if output_name:
            output_name = _sanitize_filename(output_name)

        # 圧縮形式 (個別画像時のみ有効)
        compress_idx = self.compress_combo.currentIndex()
        compress_format = ""
        if format_idx == 0 and compress_idx == 1:
            compress_format = "zip"
        elif format_idx == 0 and compress_idx == 2:
            compress_format = "cbz"

        epub_settings = {
            "enabled": format_idx == 1,
            "title": title or "Untitled",
            "author": author or "Unknown"
        }

        xtc_settings = {
            "enabled": format_idx == 2,
            "title": title or "Untitled",
            "author": author or "Unknown",
            "ext_format": "XTG" if self.xtc_bit_combo.currentIndex() == 0 else "XTH",
            "dither_algo": self.dither_algo_combo.currentText(),
            "dither_intensity": self.dither_slider.value(),
            "clean_intensity": self.clean_slider.value(),
            "clean_algo": self.clean_algo_combo.currentText(),
            "direction": self.xtc_dir_combo.currentIndex()
        }

        self.thread = ProcessingThread(
            current_images,
            output_dir,
            self.width_spin.value(),
            self.height_spin.value(),
            self.prefix_edit.text(),
            self.gray_check.isChecked(),
            self.bits_spin.value(),
            self.rename_check.isChecked(),
            self.jpeg_check.isChecked(),
            epub_settings=epub_settings,
            xtc_settings=xtc_settings,
            alignment="top" if self.alignment_combo.currentIndex() == 1 else "center",
            auto_split=self.split_check.isChecked(),
            blur_strength=self.blur_slider.value(),
            contrast=self.contrast_slider.value(),
            crop_rects=self._build_crop_rects_for_batch(current_images),
            auto_rotate=self.auto_rotate_check.isChecked(),
            sharpen=self.sharpen_slider.value(),
            clahe=self.clahe_slider.value(),
            no_resize=self.no_resize_check.isChecked(),
            output_name=output_name,
            compress_format=compress_format,
            source_labels=current_source_labels,
            source_ids=current_source_ids,
            per_folder=per_folder_enabled,
            use_source_label=use_source_label_per_group,
            split_target=self._split_target,
            split_order_h=self._split_order_h
        )
        self._error_log = []
        self.thread.progress.connect(self.update_progress)
        self.thread.finished.connect(self.on_finished)
        self.thread.log.connect(self._error_log.append)
        self.thread.start()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_finished(self, results):
        self.run_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self.thread.deleteLater()
        self.thread = None
        msg = _tr("msg_done", self._lang, n=len(results))
        if self._error_log:
            msg += _tr("msg_errors", self._lang, n=len(self._error_log)) + "\n".join(self._error_log)
        QMessageBox.information(self, _tr("dlg_done", self._lang), msg)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ImageEditorApp()
    window.show()
    sys.exit(app.exec())
