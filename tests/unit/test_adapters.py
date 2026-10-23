import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import load_model_adapter
from paa_template.config import RuntimeConfiguration
from paa_template.types import normalize_tool_call, normalize_tool_definition
from paa_template.adapters.openai_compatible import OpenAICompatibleAdapter
from paa_template.types import CompletionRequest, Message


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

    def test_new_source_kind_keeps_identity_and_ignores_extensions(self):
        tool = normalize_tool_definition({"name": "read", "description": "Read", "parameters": {}, "source": {"id": "service-1", "kind": "future-protocol"}, "extensions": {"future": "ignored"}})
        self.assertEqual(tool.source, "service-1")
        self.assertEqual(tool.source_kind, "future-protocol")
        self.assertEqual(tool.name, "read")

    def test_provider_error_chunks_are_normalized_without_raw_details(self):
        for code, capability, expected in (("model_not_found", None, "model_unavailable"), ("unsupported_capability", "image_input", "capability_unsupported")):
            def transport(_url, _payload, _headers):
                yield {"type": "error", "delta": {"code": code, "capability": capability, "message": "secret=/tmp/key"}}
            adapter = OpenAICompatibleAdapter("http://provider.local", transport=transport)
            chunks = list(adapter.stream(CompletionRequest((Message("user", "hi"),), (), True, "mock", "local")))
            self.assertEqual(chunks[0].delta["code"], expected)
            self.assertNotIn("message", chunks[0].delta)


if __name__ == "__main__":
    unittest.main()
