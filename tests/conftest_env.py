"""Подставляет фиктивные настройки, чтобы config.py читался без настоящего .env."""
import os
import sys
from pathlib import Path

os.environ.setdefault("BOT_TOKEN", "123456:TEST")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
