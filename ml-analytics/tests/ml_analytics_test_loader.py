import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "analyzer.py"
)

spec = importlib.util.spec_from_file_location(
    "ml_analytics_analyzer",
    MODULE_PATH,
)

analyzer = importlib.util.module_from_spec(spec)

spec.loader.exec_module(analyzer)
