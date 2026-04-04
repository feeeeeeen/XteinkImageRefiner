# Xteink Image Refiner

<p align="center">
  <img src="icon.png" alt="Xteink Image Refiner" width="128">
</p>

**[English README](README.md)**

漫画・自炊画像を電子書籍リーダー（特に Xteink 電子ペーパー端末）向けに最適化・変換するデスクトップアプリケーションです。

## 特徴

- **多彩な入力**: フォルダ、ZIP、個別画像ファイルから読み込み。複数ソースの追加読み込みに対応
- **画像処理パイプライン**: 余白トリミング → 自動回転 → ぼかし → リサイズ → シャープ → グレースケール → CLAHE → コントラスト → ディザリング → クリーンアップ
- **豊富な出力形式**: JPEG / PNG（フォルダ・ZIP・CBZ）、EPUB3、XTC / XTCH（Xteink 独自形式）
- **リアルタイムプレビュー**: 処理結果をズーム・パン操作で確認。前処理/出力の2モード切替
- **余白自動検出 & 手動調整**: クロップ枠をドラッグで微調整可能
- **自動分割**: 見開きページを縦横比に応じて自動2分割
- **ディザリング**: Floyd-Steinberg / Atkinson / Sauvola アルゴリズム対応（1bit / 2bit / 8bit）
- **端末プリセット**: Xteink X3 (528x792) / X4 (480x800) の解像度プリセットを内蔵
- **リサイズなしモード**: 画像のソート・リネーム・パッキング用途に対応
- **メタデータ自動取得**: `[著者名] タイトル` 形式のフォルダ/ZIP 名から自動抽出
- **日本語 / 英語 UI**: 設定画面から言語を切り替え可能
- **設定永続化**: 全設定項目をレジストリに自動保存・復元

## スクリーンショット

![Screenshot](Screenshot/screenshot_jp.png)

## 動作環境

- Windows 10 / 11
- ビルド済み exe は `dist/XteinkImageRefiner.exe` として同梱（スタンドアロン、インストール不要）

## 使い方

### exe から起動（推奨）

`dist/XteinkImageRefiner.exe` をダブルクリックするだけで使用できます。

### Python から起動

```bash
pip install PySide6 Pillow opencv-python numpy
python main.py
```

### 基本的な流れ

1. **画像を読み込む** — 「フォルダを開く」または画像リストへのドラッグ&ドロップ。ZIP ファイルも直接読み込み可能
2. **設定を調整** — リサイズ、グレースケール、ディザリング、クリーンアップ等をプレビューを見ながら調整
3. **出力** — 保存形式（個別画像 / EPUB3 / XTC）を選択し、「変換実行」ボタンで一括出力

## ビルド

PyInstaller でスタンドアロン exe をビルドできます。

```bash
pip install pyinstaller
python -m PyInstaller XteinkImageRefiner.spec
```

出力先: `dist/XteinkImageRefiner.exe`

## 独自フォーマット仕様

Xteink 端末で使用する XTG / XTH / XTC / XTCH フォーマットの仕様については以下を参照してください。

- [XTC-XTG-XTH-XTCH.md](XTC-XTG-XTH-XTCH.md)（English）
- [XTC-XTG-XTH-XTCH_jp.md](XTC-XTG-XTH-XTCH_jp.md)（日本語）

## 更新履歴

### 2026-04-04

- 端末プリセット選択（Xteink X3 528x792 / X4 480x800）を追加（旧X4チェックボックスを置き換え）
- ZIP展開時のパストラバーサル脆弱性を修正
- 余白検出スレッドの停止処理の信頼性を向上
- XTH保存処理をNumPyベクトル演算に置き換え高速化

### 2026-03-08

- 日本語 / 英語 UI言語切替機能を追加
- 著者名自動入力の改善（未検出時は「不明」ではなく空欄に変更）

### 2026-03-01

- 初回リリース

## 備考

本プロジェクトは [Claude Code](https://claude.ai/code)（Anthropic）を使用してコードを生成・開発しました。

## ライセンス

[MIT License](LICENSE)
