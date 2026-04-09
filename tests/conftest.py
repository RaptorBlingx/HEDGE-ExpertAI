"""Pytest configuration: add project root to sys.path for shared package."""

import sys
from pathlib import Path

# Add project root so shared package and top-level imports work
_root = Path(__file__).parent.parent
sys.path.insert(0, str(_root))
