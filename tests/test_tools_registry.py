"""
Pure unit tests for tools.py — no LLM or network needed.
Validates the tool registry schema and the OpenAI conversion function.
"""

import re
import pytest
from tools import TOOLS, get_openai_tools


pytestmark = pytest.mark.unit


class TestToolsRegistry:
    """Validate every tool entry in the TOOLS dict."""

    REQUIRED_TOOL_KEYS = {"description", "endpoint", "method", "parameters"}
    REQUIRED_PARAM_KEYS = {"type", "description"}
    VALID_PARAM_TYPES = {"string", "integer", "number", "boolean", "array", "object"}

    def test_all_tools_have_required_fields(self):
        for name, defn in TOOLS.items():
            missing = self.REQUIRED_TOOL_KEYS - set(defn.keys())
            assert not missing, f"Tool '{name}' missing keys: {missing}"

    def test_all_parameters_have_type_and_description(self):
        for tool_name, defn in TOOLS.items():
            for param_name, param in defn["parameters"].items():
                missing = self.REQUIRED_PARAM_KEYS - set(param.keys())
                assert not missing, (
                    f"Tool '{tool_name}' param '{param_name}' missing: {missing}"
                )

    def test_parameter_types_are_valid(self):
        for tool_name, defn in TOOLS.items():
            for param_name, param in defn["parameters"].items():
                assert param["type"] in self.VALID_PARAM_TYPES, (
                    f"Tool '{tool_name}' param '{param_name}' has invalid type: {param['type']}"
                )

    def test_required_field_is_boolean(self):
        for tool_name, defn in TOOLS.items():
            for param_name, param in defn["parameters"].items():
                if "required" in param:
                    assert isinstance(param["required"], bool), (
                        f"Tool '{tool_name}' param '{param_name}': required should be bool"
                    )

    def test_enum_values_are_lists(self):
        for tool_name, defn in TOOLS.items():
            for param_name, param in defn["parameters"].items():
                if "enum" in param:
                    assert isinstance(param["enum"], list), (
                        f"Tool '{tool_name}' param '{param_name}': enum should be a list"
                    )
                    assert len(param["enum"]) > 0, (
                        f"Tool '{tool_name}' param '{param_name}': enum should not be empty"
                    )

    def test_each_tool_has_at_least_one_required_param(self):
        for name, defn in TOOLS.items():
            has_required = any(
                p.get("required") for p in defn["parameters"].values()
            )
            assert has_required, f"Tool '{name}' has no required parameters"

    def test_endpoints_start_with_slash(self):
        for name, defn in TOOLS.items():
            assert defn["endpoint"].startswith("/"), (
                f"Tool '{name}' endpoint should start with '/': {defn['endpoint']}"
            )

    def test_method_is_post(self):
        """All current tools use POST."""
        for name, defn in TOOLS.items():
            assert defn["method"] == "POST", (
                f"Tool '{name}' method is '{defn['method']}', expected 'POST'"
            )

    def test_no_duplicate_tool_names(self):
        names = list(TOOLS.keys())
        assert len(names) == len(set(names)), "Duplicate tool names found"

    def test_tool_names_are_valid_identifiers(self):
        for name in TOOLS:
            assert re.match(r"^[a-z_][a-z0-9_]*$", name), (
                f"Tool name '{name}' is not a valid lowercase identifier"
            )


class TestGetOpenAITools:
    """Validate the OpenAI function-calling schema conversion."""

    def setup_method(self):
        self.openai_tools = get_openai_tools()

    def test_returns_list(self):
        assert isinstance(self.openai_tools, list)

    def test_count_matches_registry(self):
        assert len(self.openai_tools) == len(TOOLS)

    def test_each_tool_has_correct_structure(self):
        for tool in self.openai_tools:
            assert tool["type"] == "function"
            func = tool["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            params = func["parameters"]
            assert params["type"] == "object"
            assert "properties" in params
            assert "required" in params

    def test_required_params_match_registry(self):
        for tool in self.openai_tools:
            name = tool["function"]["name"]
            registry_def = TOOLS[name]
            expected_required = [
                p for p, d in registry_def["parameters"].items() if d.get("required")
            ]
            actual_required = tool["function"]["parameters"]["required"]
            assert sorted(actual_required) == sorted(expected_required), (
                f"Tool '{name}' required mismatch: "
                f"expected {expected_required}, got {actual_required}"
            )

    def test_enum_values_preserved(self):
        for tool in self.openai_tools:
            name = tool["function"]["name"]
            props = tool["function"]["parameters"]["properties"]
            for param_name, param_def in TOOLS[name]["parameters"].items():
                if "enum" in param_def:
                    assert props[param_name]["enum"] == param_def["enum"], (
                        f"Tool '{name}' param '{param_name}' enum not preserved"
                    )

    def test_all_registry_names_present(self):
        openai_names = {t["function"]["name"] for t in self.openai_tools}
        registry_names = set(TOOLS.keys())
        assert openai_names == registry_names
