import sys
from pathlib import Path

# Add poc root to path so tests can import element_detector and pipeline modules
sys.path.insert(0, str(Path(__file__).parent.parent))
