import sys
from pathlib import Path

# Add project root to sys.path so pytest finds 'src'
sys.path.insert(0, str(Path(__file__).parent))
