

def test_openai_sanitizer_drops_undefined_required():
    from acorn.models.openai_compat import OpenAICompatModel

    schema = {
        "type": "object",
        "properties": {"a": {"type": "string"}},
        "required": ["a", "ghost"],
        "additionalProperties": False,
    }
    out = OpenAICompatModel._sanitize_schema(schema)
    assert out["required"] == ["a"]
    assert schema["required"] == ["a", "ghost"]  # input untouched
    nested = {"type": "object", "properties": {"o": schema}, "required": ["o"]}
    assert OpenAICompatModel._sanitize_schema(nested)["properties"]["o"]["required"] == ["a"]


def test_bedrock_never_emits_empty_text_blocks():
    from acorn.models.bedrock import BedrockModel

    msgs = [
        {"role": "user", "content": ""},
        {"role": "assistant", "content": "", "tool_calls": []},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "t1", "name": "f", "args": {}}]},
        {"role": "tool", "tool_call_id": "t1", "content": ""},
    ]
    out = BedrockModel._to_messages(msgs)
    for m in out:
        for block in m["content"]:
            if "text" in block:
                assert block["text"].strip(), block
            if "toolResult" in block:
                assert all(c["text"].strip() for c in block["toolResult"]["content"])
