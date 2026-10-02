#!/usr/bin/env python3
"""python scripts/evaluate.py --reports reports/ [--output results.json]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark.evaluator.evaluate import main  # noqa: E402

sys.exit(main())
