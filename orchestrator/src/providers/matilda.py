"""Maincode Matilda provider, via matilda-agent-sdk.

The SDK is async-only; Ash's loop is synchronous. This provider owns one
dedicated event loop and drives it with run_until_complete once per turn, so
the SDK's HTTP client is reused on the same loop instead of being created and
torn down every turn.

Matilda runs the tool loop itself: it calls our async handlers, which run the
shared tools (tools/) in a worker thread, since those use blocking I/O.
History is client-side text only (the SDK takes role/content pairs), so tool
exchanges are not replayed on later turns, only what was said.
"""

import asyncio
import time

import httpx
from matilda_agent_sdk import MatildaError, ToolResult

from providers.base import Provider, ProviderError, ToolCall, TurnResult

AGENT_NAME = "ash"


class MatildaProvider(Provider):
    name = "matilda"

    def __init__(self, runner):
        self.runner = runner
        self.history = []  # [{"role": "user"|"assistant", "content": text}]
        self._loop = asyncio.new_event_loop()

    def run_turn(self, user_text, system_prompt, tool_definitions, run_tool, on_tool_call=None):
        tool_calls = []
        tool_seconds = 0.0
        first_token_at = None

        def on_token(delta):
            nonlocal first_token_at
            if first_token_at is None:
                first_token_at = time.perf_counter()

        def make_handler(name):
            async def handler(args, ctx):
                nonlocal tool_seconds
                tool_start = time.perf_counter()
                try:
                    result = await asyncio.to_thread(run_tool, name, args)
                    is_error = False
                except Exception as error:  # a tool bug must not kill the turn
                    result = f"error: {type(error).__name__}: {error}"
                    is_error = True
                tool_seconds += time.perf_counter() - tool_start
                tool_calls.append(ToolCall(name, dict(args), result))
                if on_tool_call:
                    on_tool_call(name, dict(args), result)
                return ToolResult(content=result, is_error=is_error)

            return handler

        # Neutral {name, description, parameters} is already Matilda's shape.
        client_tools = [dict(definition) for definition in tool_definitions]
        tool_handlers = {definition["name"]: make_handler(definition["name"]) for definition in tool_definitions}

        turn_start = time.perf_counter()
        try:
            result = self._loop.run_until_complete(
                self.runner.run(
                    {"name": AGENT_NAME, "instructions": system_prompt},
                    user_text,
                    history=list(self.history),
                    client_tools=client_tools,
                    tool_handlers=tool_handlers,
                    throw_on_stream_error=False,
                    callbacks={"on_token": on_token},
                )
            )
        except (MatildaError, httpx.HTTPError, TimeoutError, OSError) as error:
            raise ProviderError(f"{type(error).__name__}: {error}") from error

        if result.errors:
            details = "; ".join(f"{e.code}: {e.message}" for e in result.errors)
            raise ProviderError(f"stream error: {details}")

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": result.final_output})
        total_seconds = time.perf_counter() - turn_start
        return TurnResult(
            text=result.final_output,
            tool_calls=tool_calls,
            total_seconds=total_seconds,
            # Matilda runs its tool loop server-side too, so this includes
            # anything it does beyond the plain model call.
            model_seconds=total_seconds - tool_seconds,
            tool_seconds=tool_seconds,
            first_token_seconds=None if first_token_at is None else first_token_at - turn_start,
        )
