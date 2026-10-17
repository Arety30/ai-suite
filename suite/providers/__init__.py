"""Importing this package registers every provider against the registry."""
from suite.providers import embed, llm, vision, voice  # noqa: F401
from suite.providers.base import ProviderError, Reply, registry  # noqa: F401
