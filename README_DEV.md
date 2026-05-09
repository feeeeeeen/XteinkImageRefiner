# Xteink Image Refiner (XteinkImageRefiner) - 開発者用資料

本資料は、本ツールの仕様、ファイル構成、および開発の経緯をまとめたものです。
今後の保守や新機能追加の際に参照してください。

## 1. プロジェクト概要

Xteink 電子書籍リーダー向けに、漫画・自炊画像を最適化・変換するデスクトップアプリケーション。
フォルダ、ZIP、または個別の画像ファイルを読み込み（複数ソースの追加読み込みに対応）、前処理・リサイズ・画質補正・ディザリング・クリーンアップを行ったうえで、
個別画像（フォルダ / ZIP / CBZ）/ EPUB3 / XTC(XTG/XTH) 形式で一括出力する。
「リサイズなし」モードでは、画像のソート・リネームと複数フォルダの画像をまとめるパッキング用途にも対応。

## 2. ファイル構成

- `main.py`: PySide6 (Qt) を使用したメインGUIロジック。UI構築、イベント処理、スレッド管理を担当。
- `image_processor.py`: 画像処理コア。Pillow / OpenCV / NumPy を使用した前処理・リサイズ・画質補正・ディザリング・クリーンアップと、EPUB3 / XTC コンテナ生成、ZIP/CBZ 圧縮ロジック。
- `style.qss`: カスタムスタイルシート。ダークテーマ、:disabled グレーアウト、プレビューオーバーレイスタイルを含む。QSpinBox / QComboBox の矢印は SVG 画像で描画。
- `arrow_up.svg` / `arrow_down.svg`: QSpinBox・QComboBox 用の矢印アイコン。Qt QSS の CSS ボーダートリック非対応のため SVG で実装。PyInstaller バンドル時は絶対パス（引用符付き）に変換して適用。
- `icon.ico`: アプリケーションアイコン。マルチサイズ（16/24/32/48/64/128/256px）の Windows ICO 形式。exe に埋め込まれる。
- `icon.png`: アイコンの 256x256 PNG 版（確認・素材用）。
- `generate_icon.py`: Pillow でアイコンを生成するスクリプト。実行すると `icon.ico` と `icon.png` を出力する。
- `XteinkImageRefiner.spec`: PyInstaller ビルド定義。`style.qss`・SVG 2 ファイルの同梱、および `icon.ico` の exe 埋め込み設定を含む。
- `dist/XteinkImageRefiner.exe`: ビルド済みスタンドアロン実行ファイル。

## 3. 主要機能の技術仕様

### 3ペインUI

- **ペイン1 (設定)**: QSplitter で分割された設定エリア。グループ表示は保存形式に連動して動的に切り替わる (`setVisible`)。幅は全グループ表示時（XTC含む最大構成）の `sizeHint().width()` で `setFixedWidth` 固定されており、グループの表示/非表示でペイン幅が変動しない。設定UI要素は固定サイズで拡縮せず、余剰スペースは末尾の `addStretch()` で吸収される。最小ウィンドウ高さは設定ペインの全グループ表示時の `sizeHint().height()` から動的に算出し、UIが隠れないサイズを保証する。
  - **言語切替**: 「Settings」タイトルの右に `QComboBox`（Japanese / English）を配置。切替時に `_apply_language()` で全UIテキストを動的に更新する。コンボボックスのアイテムは選択中インデックスを保持したまま `blockSignals` で入れ替える。言語設定は `QSettings` で永続化される。
- **ペイン2 (リスト)**: `DraggableListWidget`（`QListWidget` 拡張）による並び替え。
  - `ExtendedSelection` + カスタム `dropEvent` で Ctrl+クリック複数選択 & グループドラッグを実現。
  - `blockSignals(True/False)` で移動中の `itemSelectionChanged` を抑制し、最後に `emit()` で通知。
  - `event.setDropAction(Qt.IgnoreAction)` で Qt の `InternalMove` による自動削除を防止。
  - **表示名の動的切替**: ソースが単一の場合はファイル名のみ、複数ソースの場合は `ソースラベル/ファイル名` 形式で表示（`_refresh_display_names()` で一括更新）。同一ソース内にサブフォルダがある場合は相対パス付きで表示。
  - Delete キーで選択アイテムの一括削除が可能。
  - **「全消去」ボタン**: ソートボタンの横に配置。押下で画像リスト・クロップ矩形・プレビュー・一時ディレクトリ・出力ファイル/フォルダ名（タイトル・著者名）をすべてクリアし、起動直後の状態に復元。
- **ペイン3 (プレビュー)**: `PreviewLabel`（`QLabel` 拡張）によるホイールズーム・ドラッグパン・ダブルクリックリセット。
  - `scroll_area.viewport()` の上に `QLabel#loadingOverlay` を重ね、処理中を可視化。
  - `repaint()` で同期的にフレームバッファへ書き込み、`QTimer.singleShot(0, ...)` で処理を次ループへ遅延することで、オーバーレイが DWM vsync までに確実に表示される。
  - **クロップ枠表示**: 余白トリミング有効時、前処理プレビューモードではクロップ矩形を赤枠で表示。矩形の辺・コーナーをドラッグして手動調整可能。外側は半透明黒でディム表示。
  - **プレビューモード切替**: 「前処理」(クロップ枠付き生画像) / 「出力」(フル処理パイプライン適用後) を切替ボタンで選択。選択中のボタンは `primaryButton` スタイルでハイライト。
  - **分割プレビュー切替**: 自動分割有効時、「上半分/下半分」または「左半分/右半分」の切替ボタンが動的に表示される。ラベルは画像のアスペクト比に応じて自動切替。

### 設定グループ一覧

| # | グループ | 表示条件 |
|---|---|---|
| 1 | 読み込み | 常時 |
| 2 | 前処理（自動分割・自動回転・余白トリミング・ぼかし） | 常時 |
| 3 | リサイズ（リサイズなし・プリセット・最大幅/高さ・配置・シャープ） | 常時（リサイズなし時はプリセット・幅・高さ・配置・シャープ・自動回転を無効化。プリセット選択時は最大幅・高さを無効化）|
| 4 | グレースケール（ビット数・ディザ算法/強度・コントラスト・CLAHE） | 常時（チェックOFF時はサブ設定を無効化）|
| 5 | リネーム | 常時 |
| 6 | 出力ファイル/フォルダ名（タイトル・著者名・出力名プレビュー） | 常時 |
| 7 | 保存形式（個別画像/EPUB3/XTC、JPEG変換、圧縮形式） | 常時（JPEG変換・圧縮形式は個別画像時のみ表示）|
| 8 | XTC 詳細設定 | XTC 選択時のみ表示 |

### リサイズなしモード

- グループ3の先頭に「リサイズなし」チェックボックスを配置。
- 有効時にスキップされる処理: リサイズ、自動回転、シャープ（USM）、白背景合成（パディング）。
- 有効時に無効化される UI: プリセット、最大幅/高さ、配置（ラベル含む）、シャープ（ラベル含む）、自動回転。
- 引き続き使用可能な処理: クロップ、プレぼかし、グレースケール、CLAHE、コントラスト、ディザリング、クリーンアップ。
- チェック切替時にズームスライダーを100%にリセット（出力画像サイズが大きく変わるため）。
- 用途: 画像のソート・リネームと複数フォルダの画像を1つにパッキングする際に使用。画像ごとにサイズが異なっていても問題ない。

### 出力ファイル/フォルダ名

- グループ6で「タイトル」「著者名」を入力。全出力形式共通で使用。
- **出力名プレビュー**: タイトル・著者名・出力形式・圧縮形式に応じた最終的な出力名をグレー文字で動的表示（`_update_output_name_preview`）。
  - 命名規則: `[著者名] タイトル` 形式。著者名のみの場合は `[著者名]`、タイトルのみの場合はタイトルそのまま。
  - 出力形式に応じて拡張子を切替: `フォルダ名/` / `.zip` / `.cbz` / `.epub` / `.xtc` / `.xtch`
- 入力トリガー: `textChanged` シグナルで即時更新。`on_format_changed`、`compress_combo`、`xtc_bit_combo` の変更にも連動。
- フォルダ/ZIP 名が `[著者名] タイトル` にマッチする場合は正規表現で自動抽出。
- **全消去時**: タイトル・著者名フィールドもクリア。

### 画像処理パイプライン (`resize_image`)

```
入力画像
  │
  ├─ [自動分割] 画像の縦横比で上下 or 左右に2分割
  │
  ├─ [余白トリミング] 自動検出したクロップ矩形で余白除去
  │
  ├─ [自動回転] 0° or 90°CW を自動判定（ターゲット領域を最大化）※リサイズなし時スキップ
  │
  ├─ [プレぼかし] GaussianBlur（リサイズ前。細い文字のかすれ防止）
  │
  ├─ [リサイズ] cv2.INTER_AREA（ダウンスケール時最高品質）※リサイズなし時スキップ
  │
  ├─ [シャープ] UnsharpMask（リサイズ後のエッジ復元）※リサイズなし時スキップ
  │
  ├─ [グレースケール化]
  │    ├─ [CLAHE] 局所コントラスト最適化
  │    ├─ [コントラスト] グローバルコントラスト調整
  │    └─ [量子化] ビット数に応じたレベル削減
  │
  ├─ [白背景合成] ターゲットサイズにパディング（中央 or 上寄せ）※リサイズなし時スキップ
  │
  ├─ [ディザリング] None / Floyd-Steinberg / Atkinson / Sauvola ※グレースケールまたはXTC時のみ
  │
  ├─ [クリーンアップ] Median / Bilateral フィルター
  │
  └─ [保存] JPEG / PNG / XTG / XTH
```

#### 各ステージの詳細

1. **自動分割** (`split_image_top_bottom` / `split_image_left_right`):
   - 画像の幅 ≥ 高さ（横長）→ 左右2分割
   - 画像の幅 < 高さ（縦長）→ 上下2分割
   - 奇数ピクセル時は前半側（左/上）を1px多くする

2. **余白自動トリミング** (`detect_trim_rect` / `detect_trim_rect_fast`):
   - グレースケール変換後、閾値(240)未満のピクセルを「コンテンツ」としてバイナリマスクを作成
   - 行/列のコンテンツ密度が1%未満のラインはスパースノイズ（ページ番号等）として除外
   - 安全マージン(2px)を外側に追加
   - `detect_trim_rect_fast`: バックグラウンド一括検出用。サムネイル(max 800px)で高速検出し元座標系にスケールバック
   - `TrimDetectThread`: 全画像を非UIスレッドで一括検出（絶対パスリストベース）。ユーザーの手動調整がある場合は上書きしない。追加読み込み時は `clear_existing=False` で既存の検出結果を保持
   - `PreviewLabel` でクロップ枠のドラッグ編集が可能（辺・コーナーハンドル）

3. **自動回転** (`should_auto_rotate` / `rotate_image_90cw`):
   - `min(target_w/img_w, target_h/img_h)` vs `min(target_w/img_h, target_h/img_w)` を比較
   - 回転した方がターゲット領域をより大きく使える場合に90°CW回転
   - クロップ後・リサイズ前に適用されるため、トリミング有効時はトリミング後の寸法で判定
   - **リサイズなし時はスキップ**（ターゲットサイズが存在しないため判定不可）

4. **プレぼかし** (`ImageFilter.GaussianBlur`):
   - 強度 0-100 → radius 0.0-3.0 にマッピング
   - リサイズ前に適用。細い文字がリサイズでかすれるのを防止

5. **リサイズ** (`cv2.resize` with `cv2.INTER_AREA`):
   - pixel-area-based interpolation。ダウンスケール時に LANCZOS より高品質（モアレ・エイリアシング抑制）
   - PIL → NumPy → cv2 → PIL の変換パス
   - **リサイズなし時はスキップ**（入力画像のサイズをそのまま維持）

6. **シャープ（USM）** (`ImageFilter.UnsharpMask`):
   - リサイズ後に適用し、ダウンスケールで失われたエッジを復元
   - 強度 0-100 → percent 0-150% にマッピング。radius=1.5, threshold=2 固定
   - 0 で無効（デフォルト）
   - **リサイズなし時はスキップ**（リサイズ後のエッジ復元が不要なため）

7. **CLAHE** (`cv2.createCLAHE`):
   - Contrast Limited Adaptive Histogram Equalization
   - グレースケール変換後・コントラスト調整前に適用
   - 強度 0-100 → clipLimit 0.5-4.0 にマッピング。tileGridSize=(8,8)
   - 0 で無効（デフォルト）。局所的なコントラスト改善により、影や照明ムラのあるスキャン画像で特に効果的

8. **コントラスト** (`ImageEnhance.Contrast`):
   - 強度 0-100 → factor 1.0-2.0 にマッピング
   - グレースケール後・量子化前に適用。パディング前に処理し白背景の影響を回避

9. **ディザリング** (`apply_bit_dithering`):
   - **グレースケール有効時または XTC 出力時のみ適用**。カラー出力時はスキップされ、意図しないグレースケール化を防止。
   - **None**: LUT による単純量子化。`_LUT_1BIT` / `_LUT_2BIT` で Pillow C実装テーブル参照
   - **Floyd-Steinberg**: Pillow 組み込み。事後ブレンド（量子化画像とディザ画像の混合）で白飛び制御
   - **Atkinson**: 自前実装。事前ブレンド（元画像と量子化画像の混合→ディザ適用）。Numba JIT 対応
   - **Sauvola（適応的二値化）**:
     - 1-bit: `cv2.adaptiveThreshold` (GAUSSIAN_C)。ブロックサイズは画像短辺の1/8（11-101, 奇数）
     - 2-bit: ローカル平均（`cv2.GaussianBlur`）との差分で4階調にマッピング
     - 強度 0-100 → C パラメータ 15-2 に逆マッピング（高強度ほど適応的）
     - テキスト主体の画像で特に効果的。照明ムラがある自炊スキャンとの相性が良い

10. **クリーンアップ** (`apply_cv2_cleaning`):
    - **Median**: `cv2.medianBlur` (ksize=3/5)。元画像とのブレンドで強度制御
    - **Bilateral**: `cv2.bilateralFilter` (d=9)。エッジを保持しつつノイズ除去
    - 強度 0-100 をブレンド率 (alpha) として適用

### 出力形式

- **個別画像**: JPEG/PNG。`force_jpeg` オプションで強制 JPEG 変換。quality=95。
  - **フォルダ出力**: `output_name` が指定されていればサブフォルダを自動作成してその中に出力。未指定時は選択フォルダ直下に出力。
  - **ZIP/CBZ 圧縮**: `compress_format` が `"zip"` / `"cbz"` の場合、一時フォルダに処理後、`ZIP_STORED`（無圧縮）でアーカイブ化し指定拡張子で保存。
- **EPUB3** (`create_epub`): 固定レイアウト・右綴じ (`rtl`)。画像は一時フォルダで処理後、単一 `.epub` にパック。
- **XTG** (`save_xtg`): 1-bit モノクロ独自バイナリ形式（マジック `0x00475458`）。
- **XTH** (`save_xth`): 2-bit グレースケール独自バイナリ形式（マジック `0x00485458`）。垂直スキャン・2プレーン構成・Xteink LUT マッピング。
- **XTC / XTCH** (`create_xtc`): XTG/XTH ページをまとめたコンテナ形式（マジック `0x00435458` / `0x48435458`）。メタデータ・ページインデックステーブル付き。

すべての出力形式で、`output_name` が指定されていればファイル名/フォルダ名に使用し、未指定時は従来の `[著者名] タイトル` 形式にフォールバックする。

### プレビュー更新の制御

- **デバウンス**: スピンボックス操作 → `_start_preview_timer()` → 300ms タイマー → `refresh_preview()`。スライダー操作は `sliderReleased` で直接 `refresh_preview()` を呼ぶ。
- **再入防止**: `_preview_running` フラグで二重呼び出しをガード。
- **スライダー ↔ スピンボックス同期**: `blockSignals(True/False)` でシグナル連鎖によるタイマー起動を防止。

### 入力ソース管理

- **対応入力**: フォルダ、ZIPアーカイブ、個別画像ファイル（`.jpg` / `.jpeg` / `.png` / `.bmp` / `.webp`）。
- **追加読み込み**: 新しいソースの読み込み時に既存のリストをクリアせず、追加として扱う。複数回のドロップ/選択で異なるソースの画像を一つのリストに混在させることが可能。
- **複数同時ドロップ**: ドラッグ＆ドロップで複数のフォルダ・ZIP・画像ファイルを同時に投入可能。
- **ダイアログ**: `QFileDialog.ExistingFiles`（複数選択）でフォルダ・ZIP・画像ファイルを統合選択。

#### データモデル

各リストアイテムは3つの `Qt.UserRole` データを保持する：

| ロール | 内容 | 例 |
|--------|------|-----|
| `Qt.UserRole` | 絶対ファイルパス | `C:/images/folder_a/page01.jpg` |
| `Qt.UserRole + 1` | ソースラベル（フォルダ名/ZIP名） | `folder_a` |
| `Qt.UserRole + 2` | ソース内の相対表示名 | `page01.jpg` or `sub/page01.jpg` |

パス解決は常に `Qt.UserRole`（絶対パス）を直接使用する。旧方式の `input_folder` + 相対パスの結合は廃止。

- **一時ディレクトリ**: ZIP展開用の一時ディレクトリは `self._temp_dirs`（リスト）で複数管理。ウィンドウ閉時または全消去時に一括クリーンアップ。

### 利便性機能

- **自動メタデータ取得**: フォルダ/ZIP 名が `[著者名] タイトル` の場合、正規表現で自動抽出してタイトル・著者フィールドに設定。マッチしない場合はタイトルに名前を設定し、著者名は空欄にする。
- **ZIP 読み込み**: `zipfile` で一時フォルダへ展開して処理。処理終了またはウィンドウ閉時にクリーンアップ。複数ZIPの同時展開に対応。
- **アライメント修正**: `QImage` 生成時に `bytesPerLine` を明示し、特定解像度での表示歪みを防止。
- **ファイルハンドル管理**: `with Image.open() as img: img.load(); copy = img.copy()` パターンで PIL のファイルハンドルリークを防止。
- **設定永続化**: `QSettings`（レジストリ）による全設定項目の自動保存・復元。

### 設定永続化項目

| キー | ウィジェット | デフォルト値 |
|------|-------------|-------------|
| `no_resize` | `no_resize_check` | false |
| `width` | `width_spin` | 1920 |
| `height` | `height_spin` | 1080 |
| `preset_index` | `preset_combo` | 0 (なし) |
| `alignment` | `alignment_combo` | 0 (中央寄せ) |
| `sharpen` | `sharpen_slider` | 0 |
| `split` | `split_check` | false |
| `auto_rotate` | `auto_rotate_check` | false |
| `blur_strength` | `blur_slider` | 0 |
| `grayscale` | `gray_check` | false |
| `bits` | `bits_spin` | 8 |
| `dither_algo` | `dither_algo_combo` | 0 (None) |
| `dither_intensity` | `dither_slider` | 0 |
| `contrast` | `contrast_slider` | 0 |
| `clahe` | `clahe_slider` | 0 |
| `rename` | `rename_check` | true |
| `prefix` | `prefix_edit` | "image" |
| `output_format` | `output_format_combo` | 0 (個別画像) |
| `force_jpeg` | `jpeg_check` | false |
| `compress_format` | `compress_combo` | 0 (フォルダに出力) |
| `xtc_bit` | `xtc_bit_combo` | 0 (XTG) |
| `xtc_dir` | `xtc_dir_combo` | 1 (右開き) |
| `clean_algo` | `clean_algo_combo` | 0 (Median) |
| `clean_intensity` | `clean_slider` | 0 |
| `trim_enabled` | `trim_check` | false |
| `preview_mode` | `_preview_mode` | "output" |
| `language` | `_lang` | "ja" |
| `per_folder` | `per_folder_check` | false |
| `edit_name` | `edit_name_check` | true |
| `split_target` | `_split_target` | 0 (両方) |
| `split_order_h` | `_split_order_h` | 0 (左→右) |

> **読み込み順序の依存関係**: `no_resize` → `width`/`height` → `preset_index` の順で読み込む。`on_preset_changed` 内で `no_resize_check` の状態を参照するため。旧設定キー `x4_preset` からの自動移行にも対応。
> **`edit_name` の復元**: `setChecked` を `blockSignals` で囲み、その後 `on_edit_name_changed` を明示呼び出しで1回だけ反映する（`toggled` シグナルとの二重実行防止）。

## 4. 高速化の実装詳細

### LUT による `Image.point()` 高速化

`apply_processing` および `apply_bit_dithering` 内の `point(lambda x: ...)` を、モジュールレベルの定数リスト `_LUT_1BIT` / `_LUT_2BIT` を使った `point(lut_list)` に置き換えた。リストを渡すと Pillow の C 実装が直接テーブル参照を行うため、Python の関数呼び出しオーバーヘッドを排除できる。

```python
_LUT_1BIT: list[int] = [0] * 128 + [255] * 128         # 閾値 127.5
_LUT_2BIT: list[int] = [0]*43 + [85]*85 + [170]*85 + [255]*43  # 閾値 42.5 / 127.5 / 212.5
```

### Atkinson ディザリング高速化

誤差拡散ループのボトルネックを以下の手順で改善した：

1. `np.array` → `buf.tolist()` で Python リストに変換。NumPy スカラーアクセス（〜150 ns/回）より Python リストアクセス（〜30 ns/回）の方が速い。
2. `np.argmin(np.abs(palette - val))` を単純な閾値比較（`>= 127.5` 等）に置換。
3. `target_bits` の分岐をループ外に移動し、ループ内の条件分岐を排除。
4. `row0 = buf_list[y]` のように行参照をキャッシュし、二重インデックスアクセスを削減。

### Numba JIT（オプショナル）

`numba` がインストール済みの場合のみ `@numba.njit(cache=True, nogil=True)` で Atkinson ループをコンパイルする。`nogil=True` により GIL を解放し、`ThreadPoolExecutor` との組み合わせで真の並列実行が可能になる。インストールされていない場合・例外発生時は `except Exception` で捕捉し `_NUMBA_AVAILABLE = False` のままフォールバック動作する。

```
numba==0.64.0
llvmlite==0.46.0
```

### `batch_process` の並列化

Phase 1（タスク展開）→ Phase 2（`ThreadPoolExecutor` で並列実行）→ Phase 3（順序収集・後処理）の構成。

- Phase 1: 分割・複数ファイル対応のタスクリストを事前に展開。各 sub_task に `crop()` / `copy()` で独立した PIL Image を格納しスレッド安全を確保。
- Phase 2: `max_workers=os.cpu_count()` で並列実行。`as_completed` で完了順に結果取得、`progress_callback` は単一スレッドから呼び出すため排他制御不要。
- Phase 3: `ordered_results` に元のタスクインデックスで格納し、EPUB / XTC / ZIP / CBZ 生成時の順序を保証。個別画像の ZIP/CBZ 圧縮、EPUB 生成、XTC 生成はこのフェーズで実行。

### Numba キャッシュの永続化

`--onefile` ビルドでは `sys._MEIPASS` が起動ごとに異なる一時ディレクトリになる。JIT キャッシュもその中に置かれると毎回コンパイルが走り、起動時間が数秒増加する。`main.py` の先頭で `NUMBA_CACHE_DIR` を `~/.cache/XteinkImageRefiner/` に固定することで初回コンパイル後はキャッシュが再利用される。ディレクトリ作成に失敗した場合（権限不足等）は `OSError` を捕捉して無視し、Numba は無効化されてフォールバック動作する。

### 既知の制約

- Numba 未使用時（フォールバック）の Atkinson ループは GIL を保持するため、`ThreadPoolExecutor` での Atkinson 部分の真の並列化は達成されない。I/O・リサイズ・OpenCV 処理は GIL を解放するため並列化の恩恵を受ける。
- プレビューは UI スレッドで同期実行されるため、高解像度 + Atkinson 時に数秒の無応答が発生する可能性がある（将来課題：プレビュースレッド化）。

## 5. 開発経緯

1. **初期段階**: 基本的なリサイズ・リネーム機能を備えた2ペインUI。
2. **UI刷新**: スクロールを排除し、情報密度を高めるために3ペイン構成へ移行。
3. **プレビュー操作向上**: ズームスライダーに加え、直感的なマウス操作（ホイール、ドラッグ）を専用クラスで実装。
4. **コミック特化**: EPUB3・XTC/XTG/XTH への直接変換、固定レイアウト対応、メタデータ自動化を実装。
5. **ビルド対応**: `style.qss` などのアセットを含んだスタンドアロンパッケージング化。`.spec` ファイルによる再現性確保。
6. **UI 改善**:
   - スライダー操作中に 300ms タイマーが動作する問題を `blockSignals` で修正。
   - 端末プリセット（解像度固定）コンボボックス追加。
   - グループ8を保存形式連動で `setVisible` に変更（`setEnabled` から移行）。
   - 読み込みボタンをアイコンボタン1個に統合。
   - グレースケール無効時のサブ設定グレーアウト連動。
7. **安定性向上**:
   - PIL ファイルハンドルリーク修正（`with` + `copy()` パターン）。
   - `thread.deleteLater()` によるスレッドリソース解放。
   - `DraggableListWidget` の複数選択グループドラッグ実装と `IgnoreAction` による Qt 自動削除防止。
8. **プレビューオーバーレイ**: `repaint()` + `QTimer.singleShot(0, ...)` パターンで、ペイントイベントの低優先度問題を回避し確実な表示を実現。
9. **コードレビュー対応（品質向上）**:
   - XTH 個別ページ拡張子誤り（`.xtch` → `.xth`）修正。
   - Atkinson ディザリングを NumPy 配列操作に置き換えて高速化。
   - `QSettings`（レジストリ）による設定永続化。
   - EPUB マニフェスト MIME タイプ自動判定。
   - XTC コンテナ内の UTF-8 マルチバイト文字途中カット問題を修正。
   - `QComboBox` ダークテーマスタイル追加。
10. **処理速度の最適化**: LUT 高速化、Atkinson ループ最適化、`batch_process` 並列化、Numba JIT 対応。
11. **余白自動トリミング**: `detect_trim_rect` による自動余白検出。`TrimDetectThread` で全画像をバックグラウンド一括検出。プレビューでのクロップ枠ドラッグ編集。
12. **プレビューモード切替**: 「前処理」（クロップ枠付き生画像）と「出力」（フル処理パイプライン適用後）を切り替えるトグルボタン追加。
13. **自動回転**: クロップ後・リサイズ前に 0° or 90°CW を自動判定。ターゲット領域を最大化する向きを選択。
14. **自動分割**: 従来の固定「上下2分割」を廃止。画像のアスペクト比に基づき横長→左右分割、縦長→上下分割を自動判定。手動「90度回転」も削除（自動回転でカバー）。
15. **画質向上**:
    - リサイズアルゴリズムを Pillow LANCZOS から `cv2.INTER_AREA` に変更（ダウンスケール時の品質向上）。
    - USM (UnsharpMask) によるリサイズ後のエッジ復元。
    - CLAHE（局所コントラスト最適化）による照明ムラ・影の補正。
    - Sauvola 適応的二値化による、テキスト主体画像の可読性改善。
16. **アプリケーションアイコン**: Pillow で生成したカスタムアイコン（重なった画像フレーム＋リサイズ矢印モチーフ）を `.spec` の `icon=` で exe に埋め込み。`generate_icon.py` で再生成可能。
17. **入力方式の拡張**:
    - フォルダ・ZIPに加え、個別の画像ファイル（`.jpg`/`.jpeg`/`.png`/`.bmp`/`.webp`）の直接入力に対応。
    - 読み込み時に既存データをクリアせず追加として扱うように変更。複数ソースからの画像を一つのリストに統合可能。
    - 複数ソース時はリスト表示にソースラベル（フォルダ名/ZIP名）を付与し、出所を識別可能に。
    - ドラッグ＆ドロップで複数ファイル・フォルダ・ZIPの同時投入に対応。
    - 画像一覧上部に「全消去」ボタンを追加。起動直後の状態に完全復元（タイトル・著者名も含む）。
    - データモデルを `input_folder` + 相対パスから、`Qt.UserRole` に絶対パスを格納する方式に移行。`TrimDetectThread` も絶対パスベースに変更。
18. **リサイズなしモード**:
    - 「リサイズなし」チェックボックスを追加。有効時はリサイズ・自動回転・シャープ・白背景合成をスキップし、入力画像のサイズをそのまま維持。
    - 関連 UI（プリセット・幅・高さ・配置・シャープ・自動回転）をグレーアウトで無効化（ラベル含む）。
    - チェック切替時にズームスライダーを100%にリセット。
    - グレースケール無効＋カラー出力時にディザリングが意図せずグレースケール化する問題を修正（`apply_bit_dithering` の呼び出し条件を `use_grayscale or xtc_format` に限定）。
19. **出力ファイル/フォルダ名の統合**:
    - 旧「コンテナ用メタデータ」（グループ7）を「出力ファイル/フォルダ名」（グループ6）に改称し、全出力形式で常時表示に変更。
    - 旧「保存形式」（グループ6）をグループ7に移動。
    - 出力名プレビューラベルを追加。タイトル・著者名・出力形式・圧縮形式に連動して `→ [著者名] タイトル.epub` のようにリアルタイム表示。
20. **ZIP/CBZ 圧縮出力**:
    - 個別画像出力時の圧縮オプション（フォルダに出力 / ZIP / CBZ）を追加。
    - `output_name` 指定時はサブフォルダを自動作成（フォルダ出力時）、またはアーカイブファイルを生成（ZIP/CBZ時）。
    - `ZIP_STORED`（無圧縮）で格納。JPEG/PNG は既に圧縮済みのため再圧縮の意味がなく、展開速度を優先。
21. **UIレイアウト固定化（詳細は下記）**:
    - 設定ペインのUI要素を固定サイズ化。ウィンドウサイズに依存した拡縮を排除。
    - 設定ペイン幅を全グループ表示時（XTC含む最大構成）の `sizeHint().width()` で `setFixedWidth` 固定。グループの表示/非表示でペイン幅が変動しない。
    - 最小ウィンドウ高さを設定ペインの `sizeHint().height()` から動的算出し、UIが隠れないサイズを保証。
    - 余剰スペースを `settings_layout` 末尾の `addStretch()` で吸収し、XTC表示切替時にグループ1-7の配置が変わらないようにした。
    - QSS の余白を最適化: QGroupBox の `padding` を非対称化（`8px 6px 4px 6px`）、QPushButton の `padding` を `4px 12px` に縮小、titleLabel の `font-size` を `16px` に縮小。
    - Python 側レイアウトの余白を最適化: `settings_layout` の margins を `(3,3,3,3)`・spacing を `1` に、各グループ内 margins を `(4,1,4,2)`・spacing を `2` に縮小。
22. **UI言語切替（日本語 / 英語）**:
    - モジュールレベルに `_TRANSLATIONS` 辞書（約70キー × ja/en）と `_tr(key, lang, **kwargs)` ヘルパー関数を定義。
    - 「Settings」タイトル右に言語選択 `QComboBox`（Japanese / English、幅90px固定）を配置。
    - `_on_language_changed` → `_apply_language()` で、グループボックスタイトル・チェックボックス・ラベル・ボタン・コンボボックスアイテム・プレースホルダ・ツールチップ・ダイアログメッセージ等の全UIテキストを動的更新。
    - コンボボックスのアイテム入替時は `blockSignals` で選択インデックスを保持し、シグナル連鎖による副作用を防止。
    - 英語テキストは日本語テキストと同等以下の幅に抑え、レイアウト崩れを防止（例: `ぼかし強度:` → `Blur:`、`背景クリーンアップ:` → `BG Cleanup:`）。
    - `QSettings` で言語設定を永続化（キー: `language`、デフォルト: `"ja"`）。
23. **著者名自動入力の改善**:
    - フォルダ/ZIP 名が `[著者名] タイトル` 形式にマッチしない場合、著者名フィールドを空欄にするように変更（旧: 「不明」を設定）。
24. **端末プリセットの拡充**:
    - X4 プリセット（チェックボックス）を、プリセット選択コンボボックス（なし / Xteink X3 528×792 / Xteink X4 480×800）に変更。
    - プリセット選択時は最大幅・高さを自動設定し、手動入力を無効化。「なし」選択時は手動入力が可能。
    - 旧設定キー `x4_preset` からの自動移行に対応（`preset_index` 未設定時に `x4_preset=true` なら X4 を選択）。
25. **セキュリティ・品質改善（第13回レビュー対応）**:
    - ZIP展開時のパストラバーサル対策（ZIPスリップ脆弱性修正）。`extractall` 前に全エントリのパスを `os.path.realpath` で検証。
    - `TrimDetectThread` 停止時、`wait(3000)` タイムアウト時に `terminate()` を呼び出して確実に停止させるよう改善。
    - `refresh_preview` の PIL Image 判定を `not obj` から `is None` に明示化。
    - `save_xth` のピクセル処理を Python リスト逐次ループから NumPy 配列ベクトル演算に置き換え、大幅に高速化。
26. **M5Paper S3 プリセット追加**:
    - プリセット選択コンボボックスに `M5Paper S3 (540×960)` を追加。`_PRESET_SIZES = {1: (528,792), 2: (480,800), 3: (540,960)}`。
27. **メタデータ取得の挙動変更**:
    - フォルダ/ZIP 読み込み時の `extract_metadata_from_name` 呼び出しを、画像一覧が空の場合のみに限定。複数ソース順次追加時にユーザー編集中のタイトル・著者欄が上書きされないように改善。
28. **ソート挙動の改善**:
    - `_sort_list_widget` のソートキーを絶対パスから `(ソースラベル, 相対パス)` の複合キーに変更。同一ソースの画像が必ずグループとしてまとまり、`per_folder` の挙動と整合する。
29. **フォルダごとに保存機能（バッチ処理）**:
    - 「7. 保存形式」グループに「フォルダごとに保存」チェックボックスを追加。
    - 有効時は画像一覧を**ソースID単位**でグループ化し、グループごとに `batch_process` を呼び出す。
    - 出力名は「編集する」モードに応じて切替: ON時は `<入力名>_<連番>` (3桁ゼロパディング)、OFF時は各グループのソースラベルをそのまま使用。
    - グループが1つのみの場合は通常パスにフォールバック（連番なし）。
    - 進捗バーは画像単位の全グループ通算（`processed_offset` で累積）。
    - 同名フォルダ衝突対策として、各ソース読み込み時に `_allocate_source_id` で一意なIDを発行し `Qt.UserRole + 3` に保存。`DraggableListWidget.dropEvent` / `_sort_list_widget` でも保持。
30. **「編集する」チェックボックス**:
    - 「6. 出力ファイル/フォルダ名」グループに「編集する」チェックボックスを追加（デフォルトON）。
    - OFF時はタイトル・著者欄を `setEnabled(False)` で無効化し、出力名を以下で決定:
      - `フォルダごとに保存` OFF: 最初のソースラベル（`current_source_labels[0]`）
      - `フォルダごとに保存` ON: 各グループのソースラベル（連番なし）
    - `_update_output_name_preview` を編集モードに応じてベース名を切替。
    - `load_settings` 時は `blockSignals` で `toggled` シグナル発火を抑制し、明示呼び出しで1回だけ反映。
31. **ファイル名サニタイズ（第15回レビュー対応）**:
    - モジュールレベルに `_sanitize_filename(name)` を追加。Windows予約文字 `<>:"/\|?*` および末尾のドット/空白を除去し、空文字時は `untitled` を返す。
    - `start_processing` の `output_name` 構築時、および `ProcessingThread.run` の per_folder グループ名構築時に適用。
    - ソースラベルが空の場合の警告ログ出力（`per_folder` モード時）。
32. **自動分割の仕様拡張（右綴じ漫画対応）**:
    - 「自動分割」チェックの右にコンパクトトグルボタン2つを追加:
      - **適用対象**（`split_target`）: `両方` / `左右のみ` / `上下のみ` の3状態サイクル。横長/縦長のみ分割を限定可能。
      - **左右分割の順序**（`split_order_h`）: `左→右` / `右→左` の2状態サイクル。右綴じ漫画では `右→左` を選択。
    - 上下分割は常に `上→下` 固定。
    - ボタン幅は `QFontMetrics.horizontalAdvance` で全状態テキストの最大幅を計算して `setFixedWidth` で固定（言語切替時は `_update_split_btn_widths` で再計算）。
    - 専用 QSS objectName `compactToggleButton` で `padding: 2px 6px; min-width: 0px` を上書き。
    - 自動分割 OFF 時は両トグルボタンを `setEnabled(False)` で無効化。
    - 設定値は `QSettings` で永続化（`split_target`、`split_order_h`、デフォルト 0/0）。
33. **分割画像のファイル名統一**:
    - 出力ファイル名 suffix を `_left`/`_right`/`_top`/`_bot` から `_1`/`_2` に統一。
    - `image_processor.batch_process` 内で `enumerate(sub_images, start=1)` でインデックス付与し `file_suffix = f"_{sub_idx}"` として使用。
    - 内部キー（`crop_rects` のキー、プレビュー識別子）は `"left"/"right"/"top"/"bot"` のまま維持し、ファイル名生成時のみ別変数で数字 suffix を採用。
34. **プレビュー分割切替ボタンの改善**:
    - ラベルをアスペクト比に応じた動的書き換え（「上半分/下半分」「左半分/右半分」）から固定の「1番目/2番目」（en: `Page 1`/`Page 2`）に変更。
    - 順序設定を反映: `split_order_h == 1` (右→左) の場合、1番目 = right、2番目 = left となるようプレビュー側で切替。
    - 専用 QSS objectName `splitToggleButton` で `:checked` ハイライト（`#0066cc` 背景、白文字、太字）を実装。
    - 分割対象外画像表示時はボタンを `setEnabled(False)` で無効化。`:checked:disabled` セレクタを追加してハイライトの残留を防止。
    - `_split_preview_half` の値はボタンの enabled/disabled に関わらず維持され、再度分割対象画像に戻った際にチェック状態を復元。
35. **自動分割関連の改善（第18回レビュー対応）**:
    - `TrimDetectThread` に `split_target` 引数を追加し、`apply_split` 判定をプレビュー・`batch_process` と同一ロジックで実装。`split_target=1` で縦長画像、または `split_target=2` で横長画像があっても、不要な分割クロップ検出が走らず suffix=`""` で全体検出される。
    - `_on_split_target_toggle` で `crop_rects.clear()` を削除し、`_start_trim_detection(clear_existing=False)` で既存クロップ矩形を保持。設定切替で意味が変わるキーは未参照のままメモリ上に残るが、ユーザー手動編集が消失しない。

## 6. 今後の拡張アイデア

- **PDF出力**: 画像を PDF 化して出力するオプションの追加。
- **プレビュースレッド化**: 現状の同期処理をバックグラウンドスレッドに移行し、より重いフィルター（Atkinson など）でも UI がブロックされないようにする。
- **サムネイル表示**: 画像一覧にサムネイルを表示し、視認性を向上させる。

## 7. ビルド手順

### 依存パッケージ

```
PySide6
Pillow
opencv-python-headless   # opencv-python より軽量（GUI/ffmpeg DLL 不要）
numpy
numba==0.64.0             # オプション（Atkinson JIT 高速化）。ビルドには含めない
llvmlite==0.46.0          # オプション（numba の依存）。ビルドには含めない
pyinstaller
upx                       # オプション（DLL/pyd の圧縮。インストール済みなら自動適用）
```

### ビルドコマンド

`.spec` ファイルを使用（`style.qss` および `arrow_up.svg` / `arrow_down.svg` の同梱設定が含まれる）：

```bash
python -m PyInstaller XteinkImageRefiner.spec --noconfirm
```

出力先: `dist/XteinkImageRefiner.exe`

> **注意**: SVG ファイルは QSS 内の矢印描画に必須。`.spec` の `datas` に含まれていることを確認すること。
> `load_stylesheet()` が実行時に SVG の相対 URL を `sys._MEIPASS` 絶対パスへ自動変換するため、手動での配置は不要。

> **アイコン**: `.spec` の `icon='icon.ico'` により exe にアイコンが埋め込まれる。アイコンを変更する場合は `generate_icon.py` を編集・実行して `icon.ico` を再生成し、再ビルドする。Pillow の ICO 保存では `sizes` パラメータで含めるサイズを指定し、元画像（256x256）から各サイズへ自動リサイズさせる（`append_images` は期待通り動作しないため使用しない）。

> **Numba キャッシュ**: 初回起動時に `~/.cache/XteinkImageRefiner/` へ JIT キャッシュが書き込まれる。2回目以降はキャッシュが再利用されるため起動時間が短縮される。

### ビルドサイズ最適化

`.spec` には以下のサイズ削減設定が含まれている。未最適化時の約 143 MB から **55 MB** まで削減済み。

#### 適用済みの施策

| 施策 | 効果 | 詳細 |
|------|------|------|
| PySide6 不要モジュール除外 | 大 | `excludes` で QtCore/QtGui/QtWidgets/QtSvg 以外の全 PySide6 モジュールを除外。QtSvg は QSS 内の SVG 矢印アイコン描画に必須のため残す |
| PySide6 不要 DLL 除外 | 大 | `_exclude_dll_prefixes` で Qt6WebEngine（192 MB）、Qt6Quick/Qml、opengl32sw（19 MB）等の DLL をバイナリ一覧からフィルタリング |
| numba / llvmlite 除外 | 中 | llvmlite.dll（101 MB）が巨大。`excludes` で除外。実行時は `try/except` によるフォールバックで動作 |
| opencv-python-headless 使用 | 中 | `opencv-python` の代わりに使用。GUI バインディング・ffmpeg DLL（27 MB）が不要になる。画像処理の基本関数は同一 |
| opencv_videoio_ffmpeg 除外 | 中 | ビデオ処理を行わないため DLL フィルタで除外 |
| UPX 圧縮 | 中 | `upx=True` で DLL/pyd を圧縮（例: cv2.pyd 71 MB → 17 MB）。UPX がインストール済みの場合のみ有効。CFG 保護された DLL は自動的にスキップされる |
| optimize=2 | 小 | Python バイトコードから docstring と assert を除去 |

#### 検証済みだが不採用の施策

| 施策 | 結果 | 理由 |
|------|------|------|
| strip=True | 効果なし | Windows 環境では `strip` コマンドが存在せず、WARNING が大量に出力されるだけ。strip=False を維持 |
| Nuitka 移行 | 効果なし | zstd 圧縮で 56 MB（PyInstaller の 55 MB とほぼ同一）。cv2.pyd・Qt DLL 等のバイナリ依存がボトルネックのため、Python → C コンパイルの恩恵が限定的。加えて Windows Defender の誤検知（onefile の自己展開パターンがマルウェアに類似）、Python 3.14 の実験的サポート、ビルド時間の長さ（数分 vs 数十秒）など問題が多く不採用 |

#### サイズ内訳（55 MB exe の構成、推定）

| コンポーネント | サイズ | UPX圧縮 |
|---|---|---|
| cv2.pyd | ~17 MB | 済（71 MB → 17 MB） |
| Qt6 DLL (Core+Gui+Widgets+Svg) | ~25 MB | 不可（CFG保護） |
| numpy + openblas | ~5 MB | 済 |
| Pillow | ~3 MB | 済 |
| Python ランタイム + stdlib | ~3 MB | — |
| その他 (plugins, api-ms-win 等) | ~2 MB | — |
