"""Compatibility import for development tools."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from insta_cleaner.following_parser import *  # noqa: F401,F403
