import sys
from pathlib import Path

# Make `tests.fakes` importable as `fakes` from every test file.
sys.path.insert(0, str(Path(__file__).parent))
