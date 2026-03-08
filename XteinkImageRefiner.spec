# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('style.qss', '.'), ('arrow_up.svg', '.'), ('arrow_down.svg', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # --- PySide6: QtCore / QtGui / QtWidgets 以外を除外 ---
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
        'PySide6.QtWebChannel', 'PySide6.QtWebSockets', 'PySide6.QtWebView',
        'PySide6.QtNetwork', 'PySide6.QtNetworkAuth',
        'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DAnimation',
        'PySide6.Qt3DExtras', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic',
        'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickControls2',
        'PySide6.QtQuickWidgets', 'PySide6.QtQml',
        'PySide6.QtCharts', 'PySide6.QtGraphs', 'PySide6.QtGraphsWidgets',
        'PySide6.QtDataVisualization',
        'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtSpatialAudio',
        'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtSensors',
        'PySide6.QtSerialBus', 'PySide6.QtSerialPort',
        'PySide6.QtPositioning', 'PySide6.QtLocation',
        'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtStateMachine',
        'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtTextToSpeech',
        'PySide6.QtSvgWidgets',
        'PySide6.QtAxContainer', 'PySide6.QtDBus',
        'PySide6.QtHttpServer', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtConcurrent', 'PySide6.QtXml',
        'PySide6.QtPrintSupport',
        # --- numba / llvmlite (オプション機能、フォールバック済み) ---
        'numba', 'llvmlite',
    ],
    noarchive=False,
    optimize=2,
)

# --- 不要な DLL / データをバイナリ一覧から除外 ---
# excludes は Python モジュールのみ対象のため、フック経由で追加される DLL は手動除外が必要
_exclude_dll_prefixes = (
    'Qt6WebEngine', 'Qt6Quick', 'Qt6Qml', 'Qt6OpenGL',
    'Qt6Network', 'Qt6Pdf', 'Qt6Designer',
    'Qt6Multimedia', 'Qt63D', 'Qt6Charts', 'Qt6Graphs',
    'Qt6ShaderTools', 'Qt6HttpServer', 'Qt6Bluetooth',
    'Qt6Nfc', 'Qt6Sensors', 'Qt6Serial', 'Qt6Positioning',
    'Qt6Location', 'Qt6RemoteObjects', 'Qt6Scxml',
    'Qt6StateMachine', 'Qt6Sql', 'Qt6Test', 'Qt6TextToSpeech',
    'Qt6AxContainer', 'Qt6DBus', 'Qt6Concurrent',
    'Qt6Xml', 'Qt6PrintSupport',
    'opengl32sw',
    'avcodec', 'avformat', 'avutil', 'swresample', 'swscale',
    'd3dcompiler',
    'opencv_videoio_ffmpeg',
    'Qt6VirtualKeyboard',
)
_exclude_data_prefixes = (
    'qtwebengine', 'icudtl', 'v8_context_snapshot',
    'resources/qtwebengine',
)

a.binaries = [b for b in a.binaries
              if not any(b[0].split('\\')[-1].split('/')[-1].startswith(p) for p in _exclude_dll_prefixes)]
a.datas = [d for d in a.datas
           if not any(d[0].split('\\')[-1].split('/')[-1].startswith(p) for p in _exclude_data_prefixes)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='XteinkImageRefiner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico',
)
