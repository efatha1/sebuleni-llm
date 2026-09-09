"""Error types for the strategy compiler runtime."""
from __future__ import annotations

from ._kb import UnspecifiedParameter  # re-exported: raised by the reference primitives


class CompilerError(Exception):
    """Base class."""


class DSLValidationError(CompilerError):
    """A compiled DSL document violates the schema or references an unknown identifier."""


class UnsupportedCondition(CompilerError):
    """Execution was attempted while a blocking unsupported item had no recorded operationalisation."""


class MissingParameter(CompilerError):
    """A frozen_required / frozen_choice parameter was not supplied, or was supplied off-menu."""


class MissingData(CompilerError):
    """A timeframe or instrument feed the strategy declares is absent."""
