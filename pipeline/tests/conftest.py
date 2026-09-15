import sys
from pathlib import Path

# Les scripts du pipeline s'importent comme des modules : python -m pytest tests
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
