#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
source platforms/config.sh
PLATFORM=${1:?Specify macos-arm64, macos-x64, windows-x64 or linux-x64}
ARGS=''
PY=python3
CLANG=clang
INSPECT_LLVM=
INSPECT_EXE=
case "$PLATFORM" in
  macos-arm64|macos-x64)
    export DEVELOPER_DIR="/Applications/Xcode_${XCODE_VERSION}.app/Contents/Developer"
    test -d "$DEVELOPER_DIR"
    xcodebuild -version
    ARGS+=" target_cpu=\"${PLATFORM#macos-}\" use_system_xcode=true"
    SUFFIX=dylib ;;
  windows-x64)
    export DEPOT_TOOLS_WIN_TOOLCHAIN=0
    CLANG=clang-cl.exe
    INSPECT_LLVM=$(command -v llvm-readobj.exe)
    INSPECT_LLVM=$(dirname "$INSPECT_LLVM")
    INSPECT_EXE=.exe
    command -v python3 >/dev/null || PY=python
    test -f "/c/Program Files (x86)/Windows Kits/10/Include/$WINDOWS_SDK/um/windows.h"
    ARGS+=" target_cpu=\"x64\" windows_sdk_version=\"$WINDOWS_SDK\" compute_build_timestamp=\"//angle-build-timestamp.py\""
    SUFFIX=dll ;;
  linux-x64)
    ARGS+=' target_cpu="x64" use_sysroot=true angle_use_wayland=false'
    SUFFIX=so ;;
  *) echo "Unknown platform: $PLATFORM" >&2; exit 1 ;;
esac
ROOT=$PWD
"$PY" -m unittest discover -s platforms -p 'test_*.py'
WORK="$ROOT/external/$PLATFORM"
DIST="$ROOT/dist/$PLATFORM"
mkdir -p "$WORK"
# CI starts clean. Refuse to reuse an unknown or partially prepared checkout.
test ! -e "$WORK/angle"
test ! -e "$DIST"
git init -q "$WORK/depot_tools"
git -C "$WORK/depot_tools" fetch --depth 1 https://chromium.googlesource.com/chromium/tools/depot_tools.git "$DEPOT_TOOLS_SHA"
git -C "$WORK/depot_tools" checkout -q --detach FETCH_HEAD
export DEPOT_TOOLS_UPDATE=0
export PATH="$WORK/depot_tools:$PATH"
# Pinning disables automatic initialization as well as updates.
if [[ "$PLATFORM" == windows-* ]]; then
  cmd.exe //c "$(cygpath -w "$WORK/depot_tools/bootstrap/win_tools.bat")"
fi
"$WORK/depot_tools/ensure_bootstrap"
test "$(git -C "$WORK/depot_tools" rev-parse HEAD)" = "$DEPOT_TOOLS_SHA"
git init -q "$WORK/angle"
git -C "$WORK/angle" fetch --depth 1 https://chromium.googlesource.com/angle/angle "$ANGLE_SHA"
git -C "$WORK/angle" checkout -q --detach FETCH_HEAD
cd "$WORK/angle"
"$PY" scripts/bootstrap.py
# bootstrap.py requests Android dependencies on Linux; this recipe is desktop-only.
if [[ "$PLATFORM" == linux-* ]]; then
  sed -i '/^target_os =/d' .gclient
fi
gclient sync -D --no-history
test "$(git rev-parse HEAD)" = "$ANGLE_SHA"
test "$(git -C third_party/depot_tools rev-parse HEAD)" = "$DEPOT_TOOLS_SHA"
while IFS= read -r patch; do
  git apply "$ROOT/platforms/electron-patches/$patch"
done < "$ROOT/platforms/electron-patches/.patches"
if [[ "$PLATFORM" == linux-* ]]; then
  sudo ./build/install-build-deps.sh --no-prompt --no-arm --no-chromeos-fonts
fi
if [[ "$PLATFORM" == windows-* ]]; then
  cp "$ROOT/platforms/build-timestamp.py" angle-build-timestamp.py
fi
mkdir -p out/Release
cat "$ROOT/platforms/release.gn" > out/Release/args.gn
printf '%s\n' "$ARGS" >> out/Release/args.gn
# Electron's Apple ThinLTO compiler workaround, applied to the build dependency.
git -C build apply -p2 "$ROOT/platforms/electron-build-patches/apple-thinlto.patch"
git apply "$ROOT/platforms/standalone-patches/thinlto.patch"
gn gen out/Release --fail-on-unused-args
mkdir -p "$DIST"
gn args out/Release --list --json > "$DIST/effective-args.json"
gn desc out/Release //:libANGLE cflags > "$DIST/compiler-flags.txt"
for library in libEGL libGLESv2; do
  gn desc out/Release "//:$library" ldflags > "$DIST/$library-linker-flags.txt"
done
"$PY" "$ROOT/platforms/preflight.py" "$PLATFORM" "$DIST"
{
  printf 'ELECTRON=%s\nCHROMIUM=%s\n' "$ELECTRON_VERSION" "$CHROMIUM_VERSION"
  printf 'ANGLE=%s\nDEPOT_TOOLS=%s\nPLATFORM=%s\n' "$ANGLE_SHA" "$DEPOT_TOOLS_SHA" "$PLATFORM"
  printf 'RUNNER_IMAGE=%s\n' "${ImageVersion:-unknown}"
  git -C build rev-parse HEAD
  "third_party/llvm-build/Release+Asserts/bin/$CLANG" --version
  if [[ "$PLATFORM" == macos-* ]]; then xcodebuild -version; xcrun --show-sdk-version; fi
  if [[ "$PLATFORM" == windows-* ]]; then printf 'WINDOWS_SDK=%s\n' "$WINDOWS_SDK"; fi
} > "$DIST/build-info.txt"
# Chromium's Windows compiler package omits llvm-readobj; use runner LLVM there.
if [[ -z "$INSPECT_LLVM" ]]; then
  INSPECT_LLVM="$PWD/third_party/llvm-build/Release+Asserts/bin"
fi
"$INSPECT_LLVM/llvm-readobj$INSPECT_EXE" --version > "$DIST/inspection-tools.txt"
if [[ "$PLATFORM" != windows-* ]]; then
  "$INSPECT_LLVM/llvm-nm" --version >> "$DIST/inspection-tools.txt"
fi
autoninja -C out/Release libEGL libGLESv2
cp out/Release/libEGL.$SUFFIX out/Release/libGLESv2.$SUFFIX "$DIST/"
if [[ "$PLATFORM" == windows-* && -f out/Release/d3dcompiler_47.dll ]]; then
  cp out/Release/d3dcompiler_47.dll "$DIST/"
fi
if [[ "$PLATFORM" == linux-* ]]; then
  third_party/llvm-build/Release+Asserts/bin/llvm-strip --strip-unneeded "$DIST/"*.so
fi
cp LICENSE "$DIST/ANGLE-LICENSE.txt"
cp out/Release/args.gn "$DIST/args.gn"
cp "$ROOT/platforms/config.sh" "$DIST/build-config.sh"
cp -R "$ROOT/platforms/electron-patches" "$ROOT/platforms/electron-build-patches" "$ROOT/platforms/standalone-patches" "$DIST/"
"$PY" "$ROOT/platforms/check.py" "$PLATFORM" "$DIST" \
  --llvm-bin "$INSPECT_LLVM"
