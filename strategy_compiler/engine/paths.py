"""Filesystem locations shared by the validation tests."""
import os

TESTS = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.dirname(TESTS)
ROOT = os.path.dirname(PKG)

COMPILED = os.path.join(PKG, "dsl", "compiled")
UNSUPPORTED = os.path.join(PKG, "dsl", "unsupported_registry.json")
FEATURE_REGISTRY = os.path.join(PKG, "requirements", "feature_registry.json")
MARKET_STATE = os.path.join(PKG, "requirements", "market_state_requirements.json")
TIMEFRAMES = os.path.join(PKG, "requirements", "timeframe_requirements.json")
CONFIG_S01 = os.path.join(PKG, "configs", "example_frozen_config.S01.json")

CATALOG = os.path.join(ROOT, "strategy_reearcher", "catalog")
STRATEGIES = os.path.join(CATALOG, "strategies.json")
PRIMITIVES = os.path.join(CATALOG, "primitives.json")
PARAM_REGISTER = os.path.join(CATALOG, "parameter_register.json")
