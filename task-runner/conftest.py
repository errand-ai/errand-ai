"""Shared mock setup for task-runner tests.

Mocks the agents SDK and related modules before any test file imports main.py or tool_registry.py.
Both test_main.py and test_tool_registry.py depend on these mocks.
"""

import os
import sys
from unittest.mock import MagicMock

# Add task-runner to path
sys.path.insert(0, os.path.dirname(__file__))

# Mock the agents SDK — the SDK may not be installed locally or may have
# version conflicts. We only need the pure-Python functions from main.
_mock_agents = MagicMock()
_mock_agents.function_tool = lambda f: f  # passthrough decorator
# RunHooks must be a real class so StreamEventEmitter can subclass it
_mock_agents.RunHooks = type("RunHooks", (), {})
# ModelSettings must be a real class
_mock_agents.ModelSettings = type("ModelSettings", (), {"__init__": lambda self, **kwargs: None})
sys.modules.setdefault("agents", _mock_agents)
sys.modules.setdefault("agents.mcp", MagicMock())
sys.modules.setdefault("agents.models", MagicMock())
_mock_openai_provider = MagicMock()
_mock_openai_provider.OpenAIProvider = MagicMock()
sys.modules.setdefault("agents.models.openai_provider", _mock_openai_provider)

# Mock agents.run with CallModelData and ModelInputData


class _MockModelData:
    """Simulates the model_data attribute of CallModelData."""
    def __init__(self, input_items, instructions=""):
        self.input = input_items
        self.instructions = instructions


class MockCallModelData:
    """Simulates CallModelData passed to call_model_input_filter."""
    def __init__(self, input_items, instructions=""):
        self.model_data = _MockModelData(input_items, instructions)


class MockModelInputData:
    """Simulates ModelInputData returned from call_model_input_filter."""
    def __init__(self, input, instructions=""):
        self.input = input
        self.instructions = instructions


_mock_agents_run = MagicMock()
_mock_agents_run.CallModelData = MockCallModelData
_mock_agents_run.ModelInputData = MockModelInputData
sys.modules.setdefault("agents.run", _mock_agents_run)

# Mock agents.run_context for tool_registry import


class MockRunContextWrapper:
    """Simulates RunContextWrapper."""
    def __init__(self, context=None):
        self.context = context

    def __class_getitem__(cls, item):
        return cls


_mock_run_context = MagicMock()
_mock_run_context.RunContextWrapper = MockRunContextWrapper
sys.modules.setdefault("agents.run_context", _mock_run_context)

# Mock openai — expose real exception classes so isinstance() works in _classify_error
_mock_openai = MagicMock()


class _MockAPIError(Exception):
    """Base for mock OpenAI API errors."""
    pass


class _MockAPIStatusError(_MockAPIError):
    """Mock APIStatusError with status_code attribute."""
    def __init__(self, message="", response=None, body=None):
        super().__init__(message)
        self.status_code = getattr(response, "status_code", 0) if response else 0


class _MockAPIConnectionError(_MockAPIError):
    def __init__(self, message="", request=None):
        super().__init__(message)


class _MockAPITimeoutError(_MockAPIError):
    def __init__(self, message="", request=None):
        super().__init__(message)


class _MockRateLimitError(_MockAPIStatusError):
    pass


class _MockBadRequestError(_MockAPIStatusError):
    pass


class _MockAuthenticationError(_MockAPIStatusError):
    pass


class _MockInternalServerError(_MockAPIStatusError):
    pass


_mock_openai.APIError = _MockAPIError
_mock_openai.APIStatusError = _MockAPIStatusError
_mock_openai.APIConnectionError = _MockAPIConnectionError
_mock_openai.APITimeoutError = _MockAPITimeoutError
_mock_openai.RateLimitError = _MockRateLimitError
_mock_openai.BadRequestError = _MockBadRequestError
_mock_openai.AuthenticationError = _MockAuthenticationError
_mock_openai.InternalServerError = _MockInternalServerError
_mock_openai.AsyncOpenAI = MagicMock()

sys.modules.setdefault("openai", _mock_openai)
sys.modules.setdefault("openai.types", MagicMock())
sys.modules.setdefault("openai.types.shared", MagicMock())
