import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import load_model_adapter
from paa_template.config import RuntimeConfiguration
from paa_template.types import normalize_tool_call, normalize_tool_definition


class AdapterTests(unittest.TestCase):
    def test_provider_selection_is_runtime_configured(self):
        runtime = RuntimeConfiguration("/tmp/memory", "mock", "enforced", ())
        self.assertEqual(load_model_adapter(runtime).name, "mock")
        self.assertEqual(load_model_adapter(RuntimeConfiguration("/tmp/memory", "local", "enforced", ())).name, "mock")
        self.assertEqual(
            load_model_adapter(
                RuntimeConfiguration("/tmp/memory", "openai-compatible", "enforced", ()),
                openai_compatible={"api_base_url": "http://provider.local/v1", "model": "test"},
            ).name,
            "openai-compatible",
        )
        with self.assertRaises(ValueError):
            load_model_adapter(RuntimeConfiguration("/tmp/memory", "unknown", "enforced", ()))

    def test_legacy_tool_payloads_normalize_at_boundary(self):
        tool = normalize_tool_definition({"type": "function", "function": {"name": "read", "description": "Read", "parameters": {"type": "object"}}})
        call = normalize_tool_call({"id": "call-1", "function": {"name": "read", "arguments": '{"path":"/tmp"}'}})
        self.assertEqual(tool.name, "read")
        self.assertEqual(tool.parameters["type"], "object")
        self.assertEqual(call.arguments["path"], "/tmp")


if __name__ == "__main__":
    unittest.main()
