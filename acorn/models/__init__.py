from acorn.models.anthropic import AnthropicModel
from acorn.models.base import Model, ModelTurn, ToolCall
from acorn.models.bedrock import BedrockModel
from acorn.models.gemini import GeminiModel
from acorn.models.mock import MockModel
from acorn.models.openai_compat import OpenAICompatModel

_PROVIDERS = {
    "anthropic": AnthropicModel,
    "bedrock": BedrockModel,
    "gemini": GeminiModel,
    "openai": OpenAICompatModel,
}


def resolve(spec: str, **kwargs) -> Model:
    """Build a model from ``"provider:model-name"``.

    Providers: ``anthropic`` (ANTHROPIC_API_KEY), ``gemini``
    (GEMINI_API_KEY), ``openai`` (OPENAI_API_KEY; pass ``base_url=`` for
    any OpenAI-compatible endpoint — DeepSeek, vLLM, SGLang, ...).

        resolve("anthropic:claude-sonnet-5")
        resolve("bedrock:anthropic.claude-3-5-sonnet-20241022-v2:0")
        resolve("gemini:gemini-2.5-flash")
        resolve("openai:gpt-5-mini")
        resolve("openai:deepseek-chat", base_url="https://api.deepseek.com/v1",
                api_key_env="DEEPSEEK_API_KEY")
    """
    provider, _, model = spec.partition(":")
    if provider not in _PROVIDERS:
        raise ValueError(f"unknown provider {provider!r}; known: {sorted(_PROVIDERS)}")
    if not model:
        raise ValueError(f"model name missing in spec {spec!r} (want 'provider:model')")
    return _PROVIDERS[provider](model, **kwargs)


__all__ = [
    "Model",
    "ModelTurn",
    "ToolCall",
    "AnthropicModel",
    "BedrockModel",
    "GeminiModel",
    "MockModel",
    "OpenAICompatModel",
    "resolve",
]
