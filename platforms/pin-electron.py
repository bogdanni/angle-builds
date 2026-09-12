#!/usr/bin/env python3
"""Pin ANGLE and its Electron patches to an Electron release."""
import argparse
from pathlib import Path
import re
import urllib.request


def fetch(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read().decode('utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('version', help='Electron version, for example 44.3.0')
    args = parser.parse_args()
    version = args.version.removeprefix('v')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-z]+\.\d+)?', version):
        parser.error('Expected an Electron release version')
    base = f'https://raw.githubusercontent.com/electron/electron/v{version}/'
    deps = fetch(base + 'DEPS')
    chromium = re.search(r"'chromium_version':\s*'([^']+)'", deps)[1]
    chromium_deps = fetch(f'https://raw.githubusercontent.com/chromium/chromium/{chromium}/DEPS')
    angle = re.search(r"'angle_revision':\s*'([0-9a-f]{40})'", chromium_deps)[1]
    angle_deps = fetch(f'https://raw.githubusercontent.com/google/angle/{angle}/DEPS')
    depot_tools = re.search(r'depot_tools\.git@([0-9a-f]{40})', angle_deps)[1]
    patch_list = fetch(base + 'patches/angle/.patches')
    names = [line.strip() for line in patch_list.splitlines() if line.strip() and not line.startswith('#')]
    if any(Path(name).name != name or not name.endswith('.patch') for name in names):
        raise ValueError('Unexpected patch filename')
    patches = {name: fetch(base + 'patches/angle/' + name) for name in names}
    compiler_patch = fetch(base + 'patches/chromium/build_disable_llvm_unroll-add-parallel-reductions_on_apple_targets.patch')
    root = Path(__file__).resolve().parent
    config = (root / 'config.sh').read_text()
    config = re.sub(r'^(?:ELECTRON_VERSION|CHROMIUM_VERSION)=.*\n', '', config, flags=re.M)
    config, count = re.subn(r'^ANGLE_SHA=.*$',
                          f'ELECTRON_VERSION={version}\nCHROMIUM_VERSION={chromium}\nANGLE_SHA={angle}',
                          config, flags=re.M)
    if count != 1:
        raise ValueError('Expected one ANGLE_SHA setting')
    config, count = re.subn(r'^DEPOT_TOOLS_SHA=.*$', f'DEPOT_TOOLS_SHA={depot_tools}', config, flags=re.M)
    if count != 1:
        raise ValueError('Expected one DEPOT_TOOLS_SHA setting')
    # Fetch and validate everything before replacing the previous pin.
    directory = root / 'electron-patches'
    directory.mkdir(exist_ok=True)
    for old in directory.glob('*.patch'):
        old.unlink()
    for name, text in patches.items():
        (directory / name).write_text(text)
    (directory / '.patches').write_text(''.join(name + '\n' for name in names))
    build_patches = root / 'electron-build-patches'
    build_patches.mkdir(exist_ok=True)
    (build_patches / 'apple-thinlto.patch').write_text(compiler_patch)
    (root / 'config.sh').write_text(config)
    print(f'Electron {version} -> Chromium {chromium} -> ANGLE {angle}, {len(names)} patch(es)')
    print(f'depot_tools {depot_tools} (from ANGLE DEPS)')


if __name__ == '__main__':
    main()
