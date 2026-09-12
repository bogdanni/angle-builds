"""Small GN-output fixtures exercise the checks without a source checkout."""

import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from preflight import check


class PreflightTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def fixture(self, platform):
        values = dict.fromkeys((
            "is_debug", "is_component_build", "angle_use_static_angle",
            "angle_enable_null", "angle_enable_wgpu", "angle_has_astc_encoder",
            "angle_has_frame_capture", "angle_enable_d3d11_compositor_native_window",
            "angle_enable_vulkan_validation_layers", "use_clang_modules", "is_cfi",
            "angle_use_wayland"), "false")
        values.update(dict.fromkeys(("is_official_build", "use_thin_lto",
                                     "thin_lto_enable_optimizations",
                                     "enable_stripping", "use_sysroot"), "true"))
        values.update(chrome_pgo_phase="0",
                      target_cpu=json.dumps(platform.rsplit("-", 1)[1]))
        arguments = [{"name": name, "default": {"value": value}}
                     for name, value in values.items()]
        self.write_arguments(arguments)
        windows = platform == "windows-x64"
        self.write("compiler-flags.txt", "-flto=thin /O2 /clang:-O2" if windows
                   else "-flto=thin -O2")
        linker = "/opt:lldlto=2" if windows else "-Wl,--lto-O2"
        if platform.startswith("macos-"):
            linker += " -Wcrl,strip,-x,-S"
        for library in ("libEGL", "libGLESv2"):
            self.write(f"{library}-linker-flags.txt", linker)
        return arguments

    def write(self, name, text):
        (self.directory / name).write_text(text)

    def write_arguments(self, arguments):
        self.write("effective-args.json", json.dumps(arguments))

    def test_platforms(self):
        for platform in ("macos-arm64", "macos-x64", "linux-x64", "windows-x64"):
            with self.subTest(platform=platform):
                self.fixture(platform)
                self.assertEqual(check(platform, self.directory), [])

    def test_overrides_and_missing_settings(self):
        arguments = self.fixture("linux-x64")
        for argument in arguments:
            if argument["name"] == "angle_enable_wgpu":
                argument["current"] = {"value": "true"}
        arguments = [arg for arg in arguments if arg["name"] != "is_official_build"]
        self.write_arguments(arguments)
        errors = check("linux-x64", self.directory)
        self.assertTrue(any("angle_enable_wgpu" in error for error in errors))
        self.assertTrue(any("is_official_build" in error for error in errors))

    def test_each_linker_rejects_missing_or_conflicting_lto(self):
        for platform, flag in (("linux-x64", "-Wl,--lto-O"),
                               ("windows-x64", "/opt:lldlto=")):
            for library in ("libEGL", "libGLESv2"):
                for flags in ("", flag + "0", flag + "2 " + flag + "0"):
                    with self.subTest(platform=platform, library=library, flags=flags):
                        self.fixture(platform)
                        self.write(f"{library}-linker-flags.txt", flags)
                        self.assertTrue(any(library in error
                                            for error in check(platform, self.directory)))

    def test_command_failure_report(self):
        self.fixture("linux-x64")
        self.write("libEGL-linker-flags.txt", "-Wl,--lto-O0")
        result = subprocess.run(
            [sys.executable, str(Path(__file__).with_name("preflight.py")),
             "linux-x64", str(self.directory)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("libEGL", result.stdout)
        self.assertEqual((self.directory / "preflight.txt").read_text(), result.stdout)

    def test_compiler_and_stripping(self):
        self.fixture("macos-arm64")
        self.write("compiler-flags.txt", "-O2 -O0")
        self.write("libEGL-linker-flags.txt", "-Wl,--lto-O2")
        errors = check("macos-arm64", self.directory)
        self.assertEqual(len(errors), 3)
        self.assertTrue(any("stripping" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
