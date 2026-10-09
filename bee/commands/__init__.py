"""BEE command registry — modular slash-commands for the REPL.

Adding a command (5 lines):
    # bee/commands/<name>.py
    from . import register

    @register("mycmd", "/mycmd <arg>", "one-line description")
    def mycmd(ctx, arg: str) -> str:
        return "markdown output"

    # then import it in bee/commands/__init__.py (bottom) so it self-registers.

Contract:
- handler(ctx, arg) -> str (markdown). No side effects outside the workspace.
- Errors: return an "ERROR: ..." markdown string — never raise into the REPL.
- LLM use: one focused call via ctx.client.chat("local", ...); every command
  must have a deterministic fallback for when no model is reachable.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

HANDLER = Callable  # (ctx, arg: str) -> str


@dataclass
class Command:
    name: str
    usage: str
    description: str
    handler: HANDLER


COMMANDS: dict[str, Command] = {}


def register(name: str, usage: str, description: str):
    def deco(fn: HANDLER):
        COMMANDS[name] = Command(name, usage, description, fn)
        return fn
    return deco


def get(name: str) -> Command | None:
    return COMMANDS.get(name)


def run(ctx, line: str) -> str | None:
    """line = full command line (leading '/' ok, e.g. '/draft email ...').
    Returns None if the first word is not a registered command."""
    body = line.lstrip("/").strip()
    word = body.split(None, 1)[0].lower() if body else ""
    cmd = COMMANDS.get(word)
    if cmd is None:
        return None
    arg = body[len(cmd.name):].strip()
    return cmd.handler(ctx, arg)


def help_text() -> str:
    return "\n".join(f"  {c.usage:34s} {c.description}" for c in sorted(COMMANDS.values(), key=lambda c: c.name))


# self-registration (import order: registry must exist first)
from . import plan, draft, summarize, code, think, welcome, remind  # noqa: E402,F401
