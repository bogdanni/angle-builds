# angle-builds

Build ANGLE's EGL and OpenGL ES shared libraries for macOS ARM64, macOS x64,
Windows x64, and Linux x64 on GitHub Actions. Each build uses the ANGLE source
revision and patches selected by an Electron release.

The output is a set of standalone libraries for applications that load ANGLE
directly. It does not include Electron.

## Run a build

Open **Actions → Build ANGLE → Run workflow** and select the branch to build.
Under **Platforms to build**, choose **all** or one of the four targets.

Leave **publish** unchecked to build and download artifacts without creating a
release. Once a job succeeds, its archive is available in the run's **Artifacts**
section. To publish a GitHub release, select **all** and check **publish**.
The release is created only after all four jobs succeed.

Pull requests run all four builds without publishing. Pushing a branch alone
does not start a build.

## Update the Electron version

From the repository root, run:

```sh
python3 platforms/pin-electron.py 44.3.0
```

This updates the source pins in `platforms/config.sh` and the vendored Electron
patches. It follows Electron's Chromium dependency to find the ANGLE revision,
then reads ANGLE's dependency file to select depot_tools. It also downloads
Electron's Apple ThinLTO compiler workaround.

Review the changed pins and patches before committing and pushing. The script
selects sources, but does not build them or check whether a new Electron release
requires changes to the recipe. See [Build configuration](docs/electron-build.md)
for the settings and patches to review. Then run the workflow as described above.

## Downloaded files

| Target | Archive |
|---|---|
| macOS ARM64 | `angle-macos-arm64.tar.gz` |
| macOS x64 | `angle-macos-x64.tar.gz` |
| Windows x64 | `angle-windows-x64.zip` |
| Linux x64 | `angle-linux-x64.tar.gz` |

Each archive contains `libEGL` and `libGLESv2` with the platform's native
extension, plus `ANGLE-LICENSE.txt`. Windows also includes `d3dcompiler_47.dll`
when the build produces it.

The accompanying files record how the libraries were built:

- `build-config.sh` and the patch directories identify the selected sources.
- `build-info.txt` records source revisions, compiler details, and the runner
  image version.
- `args.gn`, `effective-args.json`, and the compiler/linker flag files record
  the requested and resolved build settings.
- `preflight.txt` and `binary-report.txt` contain configuration and binary checks.
- `SHA256SUMS` contains checksums for the packaged files.

## Build environment and checks

All targets use `platforms/build.sh PLATFORM` on a fresh hosted runner. The recipe
pins Xcode, the Windows SDK, and depot_tools. ANGLE's dependency pins select the
Chromium build tools, Clang, and Linux sysroot. Hosted runner images and the
Windows Visual Studio toolset can still change.

Before compilation, the recipe checks the resolved release settings,
optimizations, and selected backends. After linking, it checks architectures,
required EGL/GLES exports, and shared-library dependencies. Unexpected settings
or dependencies fail the job. Diagnostics written before a failure are uploaded
as a separate artifact.

The macOS deployment target and Linux sysroot follow upstream ANGLE defaults.
The binary report records the resulting macOS and glibc requirements. The checks
do not impose an additional minimum-OS policy or run graphics tests. Test the
libraries in the consuming application on its supported systems.

Run the recipe's Python tests without compiling ANGLE:

```sh
python3 -m unittest discover -s platforms -p 'test_*.py'
```

## License

The workflow and scripts are MIT licensed. ANGLE's license is included in every
archive as `ANGLE-LICENSE.txt`.
