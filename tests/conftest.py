import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # the offsim package
sys.path.insert(0, str(ROOT / "skills/opt-model/scripts"))
sys.path.insert(0, str(ROOT / "tools"))
