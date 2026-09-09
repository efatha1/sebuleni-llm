#!/usr/bin/env python3
"""Run every validation test. Usage: python3 -m strategy_compiler.tests.run_all"""
from __future__ import annotations

import sys
import time
import traceback

MODULES = [
    "strategy_compiler.tests.test_dsl_schema",
    "strategy_compiler.tests.test_translation_fidelity",
    "strategy_compiler.tests.test_features",
    "strategy_compiler.tests.test_lookahead",
    "strategy_compiler.tests.test_execution",
    "strategy_compiler.tests.test_smoke_all_strategies",
]


def main() -> int:
    import importlib

    total = failed = 0
    for name in MODULES:
        mod = importlib.import_module(name)
        short = name.rsplit(".", 1)[-1]
        for attr in sorted(dir(mod)):
            if not attr.startswith("test_"):
                continue
            fn = getattr(mod, attr)
            if not callable(fn):
                continue
            total += 1
            t0 = time.time()
            try:
                fn()
                print(f"PASS  {short}.{attr}  ({time.time() - t0:.2f}s)")
            except Exception:
                failed += 1
                print(f"FAIL  {short}.{attr}")
                traceback.print_exc()
    print(f"\n{total - failed}/{total} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
