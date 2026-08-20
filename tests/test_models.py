

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
