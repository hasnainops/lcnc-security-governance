import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "scanner.py"
)

spec = importlib.util.spec_from_file_location(
    "security_scanner",
    MODULE_PATH,
)

scanner = importlib.util.module_from_spec(
    spec
)

spec.loader.exec_module(scanner)
