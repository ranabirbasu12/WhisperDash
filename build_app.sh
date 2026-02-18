#!/usr/bin/env bash
# Build WhisperDash.app bundle.
# Usage: ./build_app.sh
set -euo pipefail

VENV="./venv"
PYTHON="$VENV/bin/python"
BUNDLE="dist/WhisperDash.app"
RESOURCES="$BUNDLE/Contents/Resources"
SITE_PKGS="$VENV/lib/python3.12/site-packages"

echo "=== Cleaning previous build ==="
rm -rf build/ dist/

echo "=== Building with py2app ==="
$PYTHON setup.py py2app 2>&1 | tail -5

echo "=== Fixing namespace packages ==="
# mlx is a namespace package (no __init__.py) — py2app can't handle it.
# Remove partial mlx entries from zip, use full copy instead.
$PYTHON -c "
import zipfile, os
zip_path = '$RESOURCES/lib/python312.zip'
tmp_path = zip_path + '.tmp'
with zipfile.ZipFile(zip_path, 'r') as zin:
    with zipfile.ZipFile(tmp_path, 'w') as zout:
        for item in zin.infolist():
            if item.filename.startswith('mlx/'):
                continue
            zout.writestr(item, zin.read(item.filename))
os.replace(tmp_path, zip_path)
print('  Removed mlx/ from zip')
"

# Copy full mlx package
cp -R "$SITE_PKGS/mlx/" "$RESOURCES/lib/python3.12/mlx/"
touch "$RESOURCES/lib/python3.12/mlx/__init__.py"
# Remove py2app's partial core.so (keep original cpython-named one)
rm -f "$RESOURCES/lib/python3.12/lib-dynload/mlx/core.so" 2>/dev/null
rm -rf "$RESOURCES/lib/python3.12/lib-dynload/mlx" 2>/dev/null
echo "  Copied mlx namespace package"

# Copy PyObjCTools namespace package
cp -R "$SITE_PKGS/PyObjCTools/" "$RESOURCES/lib/python3.12/PyObjCTools/"
echo "  Copied PyObjCTools namespace package"

echo "=== Ad-hoc code signing ==="
codesign --force --deep --sign - "$BUNDLE"
xattr -cr "$BUNDLE"

echo "=== Build complete ==="
SIZE=$(du -sh "$BUNDLE" | cut -f1)
echo "  Bundle: $BUNDLE ($SIZE)"
echo ""
echo "To install: cp -R $BUNDLE /Applications/"
echo "To test:    $BUNDLE/Contents/MacOS/WhisperDash"
