"""Tests for the tool registry system."""

from __future__ import annotations

from tools.base import ToolBase
from tools.registry import ToolRegistry, register_tool


class _MockTool(ToolBase):
    """Minimal mock tool for testing registration."""

    name = "mock_tool"
    description = "A mock tool for testing"
    parameters = {
        "input": {
            "type": "string",
            "description": "Input text",
        }
    }
    aliases = ["mt", "mock"]

    async def execute(self, **kwargs):
        from tools.base import ToolOutput

        return ToolOutput(text="mock result")


class _MockToolNoAliases(ToolBase):
    """Mock tool without aliases."""

    name = "simple_tool"
    description = "A simple tool"
    parameters = {}
    aliases = []

    async def execute(self, **kwargs):
        from tools.base import ToolOutput

        return ToolOutput(text="simple result")


class TestToolRegistry:
    """Test suite for ToolRegistry."""

    def setup_method(self):
        self.registry = ToolRegistry()
        self.mock_tool = _MockTool()
        self.simple_tool = _MockToolNoAliases()

    def test_register_and_get(self):
        """Test basic tool registration and retrieval."""
        self.registry.register(self.mock_tool)
        result = self.registry.get("mock_tool")
        assert result is self.mock_tool

    def test_get_by_alias(self):
        """Test retrieving a tool by its alias."""
        self.registry.register(self.mock_tool)
        result = self.registry.get("mt")
        assert result is self.mock_tool

        result = self.registry.get("mock")
        assert result is self.mock_tool

    def test_get_case_insensitive(self):
        """Test case-insensitive tool lookup."""
        self.registry.register(self.mock_tool)
        result = self.registry.get("MOCK_TOOL")
        assert result is self.mock_tool

        result = self.registry.get("Mock_Tool")
        assert result is self.mock_tool

    def test_get_unknown_tool(self):
        """Test retrieving an unregistered tool returns None."""
        result = self.registry.get("nonexistent_tool")
        assert result is None

    def test_list_tools(self):
        """Test listing all registered tools."""
        self.registry.register(self.mock_tool)
        self.registry.register(self.simple_tool)
        tools = self.registry.list_tools()
        assert "mock_tool" in tools
        assert "simple_tool" in tools
        assert len(tools) == 2

    def test_list_with_descriptions(self):
        """Test listing tools with their descriptions."""
        self.registry.register(self.mock_tool)
        result = self.registry.list_with_descriptions()
        assert len(result) == 1
        assert result[0]["name"] == "mock_tool"
        assert result[0]["description"] == "A mock tool for testing"
        assert "mt" in result[0]["aliases"]

    def test_openai_tools_schema(self):
        """Test converting tools to OpenAI function schema."""
        self.registry.register(self.mock_tool)
        schemas = self.registry.openai_tools()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "mock_tool"
        assert "input" in schemas[0]["function"]["parameters"]["properties"]

    def test_prompt_description(self):
        """Test generating human-readable tool descriptions."""
        self.registry.register(self.mock_tool)
        prompt = self.registry.prompt_description()
        assert "mock_tool" in prompt
        assert "Mock tool" in prompt or "mock" in prompt.lower()

    def test_count_property(self):
        """Test the count property returns correct number."""
        assert self.registry.count == 0
        self.registry.register(self.mock_tool)
        assert self.registry.count == 1
        self.registry.register(self.simple_tool)
        assert self.registry.count == 2

    def test_register_duplicate_name(self):
        """Test registering a tool with the same name overwrites."""
        tool_a = _MockTool()
        tool_b = _MockTool()
        tool_b.name = "mock_tool"  # Same name

        self.registry.register(tool_a)
        self.registry.register(tool_b)

        # Should get the most recently registered
        result = self.registry.get("mock_tool")
        assert result is tool_b

    def test_global_registry_singleton(self):
        """Test that the global registry is a singleton."""
        from tools.registry import registry

        assert registry is not None
        assert isinstance(registry, ToolRegistry)


class TestRegisterToolFunction:
    """Test the standalone register_tool function."""

    def test_register_tool_function(self):
        """Test that register_tool works with the global registry."""
        from tools.registry import registry

        tool = _MockTool()
        # This should use the global registry
        register_tool(tool)

        result = registry.get("mock_tool")
        assert result is tool
