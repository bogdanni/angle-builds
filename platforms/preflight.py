#!/usr/bin/env python3
"""Check resolved GN settings before spending time compiling ANGLE."""

import argparse
import json
from pathlib import Path


def check(platform, directory):
    arguments = json.loads((directory / "effective-args.json").read_text())
    values = {arg["name"]: arg.get("current", arg["default"])["value"]
              for arg in arguments}
    expected = {
        "is_official_build": "true",
        "is_debug": "false",
        "is_component_build": "false",
        "angle_use_static_angle": "false",
        "use_thin_lto": "true",
        "thin_lto_enable_optimizations": "true",
        "chrome_pgo_phase": "0",
        "angle_enable_null": "false",
        "angle_enable_wgpu": "false",
        "angle_has_astc_encoder": "false",
        "angle_has_frame_capture": "false",
        "angle_enable_d3d11_compositor_native_window": "false",
        "angle_enable_vulkan_validation_layers": "false",
        "use_clang_modules": "false",
        "is_cfi": "false",
        "target_cpu": json.dumps(platform.rsplit("-", 1)[1]),
    }
    if platform.startswith("macos-"):
        expected["enable_stripping"] = "true"
    if platform == "linux-x64":
        expected.update(use_sysroot="true", angle_use_wayland="false")
    errors = []
    for name, value in expected.items():
        actual = values.get(name)
        if actual != value:
            errors.append(f"{name}: expected {value}, got {actual or 'missing'}")

    compiler = (directory / "compiler-flags.txt").read_text().split()
    if "-flto=thin" not in compiler:
        errors.append("libANGLE: missing -flto=thin")
    optimization = [flag for flag in compiler
                    if flag in ("-O0", "-O1", "-O2", "-O3", "-Os", "-Oz",
                                "/Od", "/O1", "/O2", "/clang:-O2")]
    if not optimization or optimization[-1] not in ("-O2", "/O2", "/clang:-O2"):
        errors.append(f"libANGLE: expected effective O2, got {optimization}")

    windows = platform == "windows-x64"
    lto = "/opt:lldlto=2" if windows else "-Wl,--lto-O2"
    for library in ("libEGL", "libGLESv2"):
        flags = (directory / f"{library}-linker-flags.txt").read_text().split()
        levels = [flag for flag in flags
                  if flag.startswith(("-Wl,--lto-O", "/opt:lldlto="))]
        if not levels or any(flag != lto for flag in levels):
            errors.append(f"{library}: expected {lto}, got {levels}")
        if platform.startswith("macos-") and "-Wcrl,strip,-x,-S" not in flags:
            errors.append(f"{library}: missing macOS stripping flags")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("platform", choices=("macos-arm64", "macos-x64",
                                             "linux-x64", "windows-x64"))
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    errors = check(args.platform, args.directory)
    report = "Preflight failed:\n" + "\n".join(errors) if errors else "Preflight passed"
    (args.directory / "preflight.txt").write_text(report + "\n")
    print(report)
    raise SystemExit(bool(errors))


if __name__ == "__main__":
    main()
