"""Tests for MCP config parsing, tool adapters, and cost tracking."""

from __future__ import annotations

import json


class TestMCPConfig:
    def test_load_config(self, tmp_path):
        from core.mcp_client import load_mcp_config

        config_file = tmp_path / "mcp_config.json"
        config_file.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "test-server": {
                            "command": "echo",
                            "args": ["hello"],
                            "env": {"FOO": "bar"},
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        servers = load_mcp_config(str(config_file))
        assert "test-server" in servers
        assert servers["test-server"].command == "echo"
        assert servers["test-server"].args == ["hello"]
        assert servers["test-server"].env["FOO"] == "bar"

    def test_load_config_empty(self, tmp_path):
        from core.mcp_client import load_mcp_config

        servers = load_mcp_config(str(tmp_path / "nonexistent.json"))
        assert servers == {}

    def test_load_config_invalid_json(self, tmp_path):
        from core.mcp_client import load_mcp_config

        config_file = tmp_path / "mcp_config.json"
        config_file.write_text("{invalid json", encoding="utf-8")
        servers = load_mcp_config(str(config_file))
        assert servers == {}

    def test_tool_adapter_naming(self):
        from core.mcp_client import MCPManager, MCPToolSchema
        from tools.mcp_tools import MCPToolAdapter

        schema = MCPToolSchema(name="read_file", description="Read a file")
        manager = MCPManager()
        adapter = MCPToolAdapter("filesystem", schema, manager)
        assert adapter.name == "mcp__filesystem__read_file"
        assert "filesystem" in adapter.description

    def test_tool_adapter_parameters(self):
        from core.mcp_client import MCPManager, MCPToolSchema
        from tools.mcp_tools import MCPToolAdapter

        schema = MCPToolSchema(
            name="search",
            description="Search files",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {"type": "integer", "description": "Max results"},
                },
                "required": ["query"],
            },
        )
        manager = MCPManager()
        adapter = MCPToolAdapter("search-srv", schema, manager)
        assert "query" in adapter.parameters
        assert "limit" in adapter.parameters
        assert adapter.parameters["query"]["required"] is True


class TestCostTracking:
    def test_cost_tracker_summary(self):
        from llm import CostTracker

        tracker = CostTracker()
        tracker.add_usage({"prompt_tokens": 1000, "completion_tokens": 500}, "glm-4.5")
        summary = tracker.summary()
        assert "glm-4.5" in summary
        assert "Tokens" in summary
        assert "Cost" in summary

    def test_cost_tracker_to_dict(self):
        from llm import CostTracker

        tracker = CostTracker()
        tracker.add_usage({"input_tokens": 100, "output_tokens": 50}, "gpt-4o")
        d = tracker.to_dict()
        assert d["input_tokens"] == 100
        assert d["output_tokens"] == 50
        assert d["model"] == "gpt-4o"

    def test_cost_tracker_reset(self):
        from llm import CostTracker

        tracker = CostTracker()
        tracker.add_usage({"prompt_tokens": 1000, "completion_tokens": 500}, "glm-4.5")
        tracker.reset()
        assert tracker.total_input_tokens == 0
        assert tracker.total_output_tokens == 0
        assert tracker.total_cost == 0.0

    def test_cost_tracker_glm_pricing(self):
        from llm import CostTracker

        tracker = CostTracker()
        tracker.add_usage({"prompt_tokens": 1000000, "completion_tokens": 1000000}, "glm-4.5")
        d = tracker.to_dict()
        # glm-4.5: $0.60/M input + $2.20/M output = $2.80
        assert abs(d["cost"] - 2.80) < 0.01
