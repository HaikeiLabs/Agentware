"""Test configuration."""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
print(f"[conftest] Added {project_root} to sys.path")
print(f"[conftest] sys.path[0] = {sys.path[0]}")
