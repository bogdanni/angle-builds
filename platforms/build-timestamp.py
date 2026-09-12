#!/usr/bin/env python3
"""Use ANGLE's commit time for standalone Windows build metadata."""
from pathlib import Path

print(int((Path(__file__).resolve().parent / 'build/util/LASTCHANGE.committime').read_text()))
