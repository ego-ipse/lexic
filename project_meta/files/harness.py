"""VyxHarness — grammar-driven agent harness via pydantic-ai.

Grammar → models → pydantic-ai Agent → validated VyxBase.

Provider string follows pydantic-ai conventions:
    "anthropic:claude-sonnet-4-6"
    "openai:gpt-4o"
    "openai:local"           llama-server via OpenAI-compatible endpoint
    "ollama:qwen2.5-coder"   Ollama with format field

For token-level constraint on llama.cpp, use for_llama_cpp() which
passes a custom OpenAIModel pointed at llama-server directly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from base import VyxBase
from builder import GBNFModelBuilder
from gbnf import GBNFParser

_GRAMMAR_PATH = Path(__file__).parent.parent / "grammar.gbnf"


class VyxHarness:
    """Grammar-driven agent harness.

    Grammar is the source of truth.
    pydantic-ai owns provider abstraction, structured output, retry.
    VyxBase owns the indexing layer after validation.
    """

    def __init__(
        self,
        grammar: str,
        model: "str | Any",
        **agent_kwargs: Any,
    ) -> None:

        self._grammar = grammar
        self._model = model
        self._agent_kwargs = agent_kwargs
        self._rules = GBNFParser().parse(grammar)
        self.registry = GBNFModelBuilder(self._rules).build()
        self._agents: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_grammar_file(
        cls,
        path: str | Path | None = None,
        model: "str | Any" = "anthropic:claude-sonnet-4-6",
        **agent_kwargs: Any,
    ) -> VyxHarness:
        """Load grammar from file (default: bundled grammar.gbnf)."""
        grammar = Path(path or _GRAMMAR_PATH).read_text()
        return cls(grammar, model, **agent_kwargs)

    @classmethod
    def for_llama_cpp(
        cls,
        grammar: str | None = None,
        host: str = "localhost:8080",
        model_id: str = "local",
        **kwargs: Any,
    ) -> VyxHarness:
        """Token-level constraint via llama-server json_schema field."""
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIModel

        g = grammar or Path(_GRAMMAR_PATH).read_text()
        m = OpenAIModel(
            model_id,
            openai_client=AsyncOpenAI(
                base_url=f"http://{host}/v1",
                api_key="not-required",
            ),
        )
        return cls(g, m, **kwargs)

    @classmethod
    def for_anthropic(
        cls,
        grammar: str | None = None,
        model_id: str = "claude-sonnet-4-6",
        **kwargs: Any,
    ) -> VyxHarness:
        g = grammar or Path(_GRAMMAR_PATH).read_text()
        return cls(g, f"anthropic:{model_id}", **kwargs)

    @classmethod
    def for_openai(
        cls,
        grammar: str | None = None,
        model_id: str = "gpt-4o",
        **kwargs: Any,
    ) -> VyxHarness:
        g = grammar or Path(_GRAMMAR_PATH).read_text()
        return cls(g, f"openai:{model_id}", **kwargs)

    @classmethod
    def for_ollama(
        cls,
        grammar: str | None = None,
        model_id: str = "qwen2.5-coder:7b",
        host: str = "localhost:11434",
        **kwargs: Any,
    ) -> VyxHarness:
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIModel

        g = grammar or Path(_GRAMMAR_PATH).read_text()
        m = OpenAIModel(
            model_id,
            openai_client=AsyncOpenAI(
                base_url=f"http://{host}/v1",
                api_key="not-required",
            ),
        )
        return cls(g, m, **kwargs)

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def emit(self, rule: str, prompt: str, **kwargs: Any) -> VyxBase:
        """Return a validated model instance for the given grammar rule."""
        return self._agent(rule).run_sync(prompt, **kwargs).data

    async def emit_async(self, rule: str, prompt: str, **kwargs: Any) -> VyxBase:
        """Async variant of emit."""
        result = await self._agent(rule).run(prompt, **kwargs)
        return result.data

    # ------------------------------------------------------------------
    # Runtime mutations
    # ------------------------------------------------------------------

    def swap_model(self, model: "str | Any") -> None:
        """Switch provider. Grammar and models unchanged."""
        self._model = model
        self._agents.clear()

    def rebuild(self, grammar: str) -> None:
        """Rebuild registry from updated grammar after !H L4 mutation.

        Call at the next !W boundary.
        """
        self._grammar = grammar
        self._rules = GBNFParser().parse(grammar)
        self.registry = GBNFModelBuilder(self._rules).build()
        self._agents.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _agent(self, rule: str) -> Any:
        if rule not in self._agents:
            from pydantic_ai import Agent

            if rule not in self.registry:
                raise KeyError(
                    f"rule {rule!r} not in grammar. Available: {sorted(self.registry)}"
                )
            self._agents[rule] = Agent(
                self._model,
                result_type=self.registry[rule],
                **self._agent_kwargs,
            )
        return self._agents[rule]
