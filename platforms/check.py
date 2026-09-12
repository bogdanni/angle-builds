#!/usr/bin/env python3
"""Inspect packaged libraries without executing target-platform code."""
import argparse
import hashlib
from pathlib import Path
import re
import subprocess


def version(value):
    return tuple(int(part) for part in value.split('.'))


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('platform', choices=['macos-arm64', 'macos-x64', 'linux-x64', 'windows-x64'])
    parser.add_argument('directory', type=Path)
    parser.add_argument('--llvm-bin', type=Path, required=True)
    args = parser.parse_args()
    windows = args.platform.startswith('windows')
    mac = args.platform.startswith('macos')
    suffix = '.dll' if windows else '.dylib' if mac else '.so'
    executable = '.exe' if (args.llvm_bin / 'llvm-readobj.exe').exists() else ''

    def run(tool, *options):
        return subprocess.check_output([str(args.llvm_bin / (tool + executable)), *map(str, options)], text=True)

    linux_deps = {'ld-linux-x86-64.so.2', 'libc.so.6', 'libdl.so.2', 'libm.so.6',
                  'libpthread.so.0', 'librt.so.1', 'libgcc_s.so.1', 'libX11.so.6',
                  'libXext.so.6', 'libxcb.so.1'}
    windows_deps = {'kernel32.dll', 'user32.dll', 'gdi32.dll', 'advapi32.dll',
                    'shell32.dll', 'ole32.dll', 'oleaut32.dll', 'shlwapi.dll',
                    'version.dll', 'ws2_32.dll', 'ntdll.dll', 'bcrypt.dll',
                    'crypt32.dll', 'setupapi.dll', 'cfgmgr32.dll', 'd3d11.dll',
                    'dxgi.dll', 'd3d9.dll', 'dxguid.dll', 'opengl32.dll', 'dwmapi.dll',
                    'powrprof.dll', 'combase.dll', 'ucrtbase.dll', 'rpcrt4.dll'}
    report = []
    for stem in ['libEGL', 'libGLESv2']:
        require((args.directory / (stem + suffix)).is_file(), f'Missing {stem}{suffix}')
    for library in sorted(args.directory.glob('*' + suffix)):
        options = ['--file-headers', '--needed-libs']
        options += ['--coff-imports'] if windows else ['--macho-version-min'] if mac else ['--version-info']
        data = run('llvm-readobj', *options, library)
        expected = 'aarch64' if args.platform == 'macos-arm64' else 'x86_64'
        require(f'Arch: {expected}\n' in data, f'{library.name}: wrong architecture')
        report.append(data)
        (args.directory / 'binary-report.txt').write_text('\n'.join(report))
        if windows:
            deps = re.findall(r'Import \{\s+Name: (\S+)', data)
            require(bool(deps), f'{library.name}: no import information')
            for dep in deps:
                require(dep.lower() in windows_deps or dep.lower().startswith(('api-ms-win-', 'ext-ms-win-'))
                        or any(p.name.lower() == dep.lower() for p in args.directory.glob('*.dll')),
                        f'{library.name}: unpackaged dependency {dep}')
        else:
            match = re.search(r'NeededLibraries \[([^]]*)\]', data)
            require(match is not None, f'{library.name}: no dependency information')
            for dep in match[1].split():
                if mac:
                    allowed = dep.startswith(('/System/Library/', '/usr/lib/')) or (
                        dep.startswith(('@rpath/', '@loader_path/', './')) and (args.directory / Path(dep).name).is_file())
                else:
                    allowed = dep in linux_deps or (args.directory / dep).is_file()
                require(allowed, f'{library.name}: unexpected dependency {dep}')
        if mac:
            minimums = re.findall(r'\n  Version: ([0-9.]+)', data)
            require(bool(minimums), f'{library.name}: missing deployment target')
            print(f'{library.name}: minimum macOS {max(minimums, key=version)}')
        elif not windows:
            requirements = re.findall(r'GLIBC_([0-9.]+)', data)
            require(bool(requirements), f'{library.name}: missing glibc requirements')
            print(f'{library.name}: requires glibc {max(requirements, key=version)}')
            require('GLIBCXX_' not in data, f'{library.name}: unexpected system libstdc++ dependency')
        if library.stem in ('libEGL', 'libGLESv2'):
            if windows:
                symbols = run('llvm-readobj', '--coff-exports', library)
                names = set(re.findall(r'\n  Name: (\S+)', symbols))
            else:
                flags = ['--extern-only', '--defined-only', '--format=posix']
                if not mac:
                    flags.append('--dynamic')
                symbols = run('llvm-nm', *flags, library)
                names = {line.split()[0].removeprefix('_') for line in symbols.splitlines() if line.strip()}
            needed = {'eglGetProcAddress', 'eglInitialize', 'eglCreateContext'} if library.stem == 'libEGL' else {'glGetString', 'glDrawArrays', 'glCreateShader'}
            require(needed <= names, f'{library.name}: missing exports {needed - names}')
        print(f'Checked {library.name}')
    files = sorted(p for p in args.directory.rglob('*') if p.is_file() and p.name != 'SHA256SUMS')
    (args.directory / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(args.directory).as_posix()}\n' for p in files))


if __name__ == '__main__':
    main()
