import sys
from pathlib import Path

# Make the fake upstream importable as a plain module without turning tests/ into a package.
sys.path.insert(0, str(Path(__file__).parent))
