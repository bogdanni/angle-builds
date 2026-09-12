# Build configuration

This recipe uses Electron's ANGLE source revision and ANGLE patches to produce
standalone EGL/GLES shared libraries. It follows Electron's release settings
where they apply to those libraries, while using ANGLE's own build dependencies.
It does not reproduce Electron's complete build environment or binaries.

The current pins are in [`platforms/config.sh`](../platforms/config.sh). The
references below describe Electron 44.3.0, Chromium 152.0.7977.78, and ANGLE
`736ed80c7552a4b267bd54a282b971aa4555cb3e`.

## Release settings

[`platforms/release.gn`](../platforms/release.gn) selects upstream official release
mode with `is_official_build=true` and `is_component_build=false`. This enables
ThinLTO and macOS stripping through upstream defaults, and disables the null and
experimental WebGPU backends. Setting only `is_debug=false` would not select the
same release configuration.

The recipe disables profile-guided optimization (PGO). It does not use Electron's
application workload profiles. It retains Electron's settings that disable Clang
modules, CFI, and Vulkan validation layers.

ASTC encoding and D3D11 compositor-native windows are enabled by standalone ANGLE
defaults but not by Chromium's embedded configuration. The recipe disables both,
as well as frame capture.

## Patches needed for ThinLTO

Two patches supplement Electron's ANGLE patch list:

- **Apple compiler workaround.** The version resolver downloads Electron's patch
  for incorrect loop reductions during ThinLTO. The build applies it to ANGLE's
  Chromium build dependency.
- **Shared-library optimization.** ANGLE's standalone EGL/GLES targets otherwise
  inherit level-zero ThinLTO optimization, even in official mode. The local patch
  selects upstream's `thinlto_optimize_max` configuration for both libraries.
  It removes the default through ANGLE's `suppressed_configs`, which reaches the
  underlying target rather than just its wrapper.

Before compilation, the resolved linker flags must select `--lto-O2`, or
`/opt:lldlto=2` on Windows, for both libraries.

## Differences from Electron

| Area | This recipe |
|---|---|
| Library layout | Builds EGL/GLES shared libraries. Electron 44 embeds ANGLE statically. |
| PGO | Disabled. Electron's application profiles are not used. |
| Dependencies | Uses ANGLE's pinned compiler, build tools, depot_tools, and Linux sysroot. These can differ from Electron's surrounding Chromium build. |
| SDKs | Pins Xcode and the Windows SDK. The Visual Studio toolset follows the hosted runner. |
| OS requirements | Uses upstream ANGLE's macOS deployment target and Linux sysroot. It does not import Electron's custom Linux sysroot. |
| C++ runtime | Links libc++ statically into the shared libraries. Electron's libc++ ABI patch for native Node modules is not applied to this EGL/GLES C interface. |
| Allocation and threading | Uses ANGLE's standalone implementation, without Chromium's allocator and task integration. |
| Vulkan on macOS | Retains the backend and its statically linked loader. Chromium uses a separate shared loader. |
| Linux display support | Enables X11 and disables Wayland. |
| Windows build timestamp | Uses the ANGLE commit time. Chromium's default official-build timestamp script requires `chrome/VERSION`, which is absent here. |
| Stripping | Uses upstream macOS stripping and explicitly strips packaged Linux libraries with LLVM. Windows archives omit separate PDB files. |

## Checks and their limits

GN rejects unused arguments. [`preflight.py`](../platforms/preflight.py) then
checks the resolved build mode, architecture, backends, PGO setting, compiler
optimization, ThinLTO flags, and macOS stripping flags. Missing or unexpected
values stop the build before compilation.

After linking, [`check.py`](../platforms/check.py) checks library architectures,
selected EGL/GLES exports, and dependencies. It records macOS deployment targets
and glibc requirements without imposing a separate compatibility ceiling.

These checks detect configuration changes and packaging problems. They do not
measure performance, establish compatibility with every supported OS version,
or test graphics drivers. Those require running the libraries in the consuming
application.

## When updating Electron

Review Electron's release arguments and ANGLE overrides alongside the new source
pins and patch list. The Apple compiler workaround and local ThinLTO patch may
need revision as upstream changes. The resolver expects the named Apple patch
to exist and stops if it cannot download it.

Build all four targets after changing the pins. Review the resolved flags and
binary reports, especially deployment targets and dependencies, before using
the libraries. A successful build on one target does not establish the result
on the others.

## Upstream references

- [Electron release arguments](https://github.com/electron/electron/blob/v44.3.0/build/args/release.gn)
- [Electron common arguments](https://github.com/electron/electron/blob/v44.3.0/build/args/all.gn)
- [ANGLE feature defaults](https://github.com/google/angle/blob/736ed80c7552a4b267bd54a282b971aa4555cb3e/gni/angle.gni)
- [Chromium ANGLE overrides](https://github.com/chromium/chromium/blob/152.0.7977.78/build_overrides/angle.gni)
- [Electron Apple compiler workaround](https://github.com/electron/electron/blob/v44.3.0/patches/chromium/build_disable_llvm_unroll-add-parallel-reductions_on_apple_targets.patch)
- [Electron C++ ABI patch](https://github.com/electron/electron/blob/v44.3.0/patches/chromium/build_make_libcxx_abi_unstable_false_for_electron.patch)
