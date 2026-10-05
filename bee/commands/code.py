"""/code — production-grade code generation + systematic debugging.

Usage:
  /code <task…>                      language auto-detected (Python default)
  /code python|bash|js|ts <task…>    explicit language
  /code debug <code + observed error>  systematic debug pass

Output contract: single fenced code block, runnable, type hints (py) / strict
style (ts/js), error handling, comments on non-obvious lines, plus a minimal
test snippet. LLM-driven when reachable; honest skeleton fallback otherwise.
"""
from __future__ import annotations

import re
from datetime import date

from . import register

LANGS = ("python", "py", "bash", "sh", "shell", "js", "ts", "typescript", "javascript")
FENCE = {"python": "python", "py": "python", "bash": "bash", "sh": "bash", "shell": "bash",
         "js": "javascript", "ts": "typescript", "typescript": "typescript", "javascript": "javascript"}

PROMPTS = {
    "python": "Write production-grade Python 3.10+ for the task below. Requirements: type hints, "
              "docstring, input validation, explicit error handling (no bare except), no placeholder "
              "logic, stdlib-first, one fenced ```python block, then a '## Tests' section with 2-3 "
              "doctest or pytest snippets. No prose before the code.",
    "bash": "Write a robust Bash script for the task below. Requirements: set -euo pipefail, "
            "quoted variables, input validation, error messages to stderr, one fenced ```bash block, "
            "then '## Tests' with 2-3 invocation examples. No prose before the code.",
    "js": "Write production-grade JavaScript (Node 18+) for the task below. Requirements: JSDoc on "
          "exports, input validation, explicit error handling, no silent catches, one fenced ```js "
          "block, then '## Tests' with 2-3 node --test snippets. No prose before the code.",
    "ts": "Write production-grade TypeScript (strict) for the task below. Requirements: explicit "
          "types, no any, input validation, explicit error handling, one fenced ```ts block, then "
          "'## Tests' with 2-3 vitest snippets. No prose before the code.",
}


def _detect_lang(arg: str) -> tuple[str, str]:
    words = arg.split()
    if words and words[0].lower() in LANGS:
        return FENCE[words[0].lower()], " ".join(words[1:])
    low = arg.lower()
    if re.search(r"\b(bash|shell script|\.sh|chmod|pipefail|grep|awk|sed)\b", low):
        return "bash", arg
    if re.search(r"\b(typescript|\.ts\b|interface |readonly |<T>|tsx)\b", low):
        return "typescript", arg
    if re.search(r"\b(javascript|node(js)?|\.js\b|npm|console\.log|require\(|import .* from)\b", low):
        return "javascript", arg
    return "python", arg  # default


def _skeleton(lang: str, task: str) -> str:
    t = re.sub(r"\s+", " ", task)[:120]
    if lang == "python":
        return (
            "```python\n"
            f'\"\"\"{t[:80]}\n\nDeterministic skeleton (no model reachable) — fill the marked sections.\n\"\"\"\n'
            "from __future__ import annotations\n\n\n"
            "def main(input_data: str) -> str:\n"
            "    \"\"\"Entry point. Validate input, do the work, return a result.\"\"\"\n"
            "    if not input_data or not input_data.strip():\n"
            "        raise ValueError(\"input_data must be a non-empty string\")\n"
            "    # TODO(1): core logic\n"
            "    # TODO(2): edge cases (empty sections, malformed rows, unicode)\n"
            "    # TODO(3): logging via the `logging` module (never print in library code)\n"
            "    return input_data.strip()\n\n\n"
            "if __name__ == \"__main__\":\n"
            "    raise SystemExit(main(\"<sample input>\"))\n"
            "```\n\n## Tests\n```python\nassert main(\"  x  \") == \"x\"\ntry:\n    main(\"\")\nexcept ValueError:\n    pass\nelse:\n    raise AssertionError\n```\n"
            "_(LLM offline — skeleton only. Retry when Ollama is up for real logic.)_"
        )
    if lang == "bash":
        return (
            "```bash\n#!/usr/bin/env bash\nset -euo pipefail\n# " + t + "  (skeleton — LLM offline)\n"
            "main() {\n  local input=\"${1:?usage: script.sh <input>}\"\n  echo \"$input\" >&2 || true\n  # TODO: core logic\n}\nmain \"$@\"\n```\n\n"
            "## Tests\n```bash\n./script.sh sample && echo ok\n```\n"
            "_(LLM offline — skeleton only.)_"
        )
    return (
        f"```{lang if lang != 'typescript' else 'ts'}\n// {t}  (skeleton — LLM offline)\n"
        "function main(input: string): string {\n  if (!input || !input.trim()) throw new Error('input required');\n"
        "  // TODO: core logic + edge cases\n  return input.trim();\n}\nexport { main };\n```\n\n"
        "## Tests\n```ts\nimport { main } from \"./file\";\nconsole.assert(main(\" x \") === \"x\");\n```\n"
        "_(LLM offline — skeleton only.)_"
    )


def _debug_fallback(code: str) -> str:
    errs = re.findall(r"[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception)\b[^\n]{0,100}", code)
    lines = [f"## Systematic debug pass (deterministic — no model reachable)\n"]
    if errs:
        lines.append("### Detected error signatures")
        lines += [f"- `{e.strip()[:140]}`" for e in list(dict.fromkeys(errs))[:5]]
    else:
        lines.append("- no error signature detected in input — paste the full traceback")
    lines += [
        "",
        "### Method (run top-down)",
        "1. **Reproduce** — smallest input that triggers it (write it as a failing test first).",
        "2. **Localize** — binary search: comment out halves of the code path until the failure moves.",
        "3. **Hypothesis** — state the cause in one sentence; check types at the boundary (`repr()`/`typeof`).",
        "4. **Fix + regression test** — fix the cause, not the symptom; the new test must fail pre-fix.",
        "5. **Check invariants** — off-by-one at loops, mutation of shared state, encoding, async ordering.",
        "",
        f"Input size: {len(code)} chars. Retry when the local model is reachable for a line-level analysis.",
    ]
    return "\n".join(lines)


def _llm(ctx, prompt: str, max_tokens: int = 1400) -> str | None:
    if ctx is None or ctx.client is None:
        return None
    try:
        out = ctx.client.chat("local", [{"role": "user", "content": prompt}], max_tokens=max_tokens)
        c = (out.get("content") or "").strip()
        return c or None
    except Exception:
        return None


def _save(text: str, tag: str):
    from .. import paths
    d = paths.WORKSPACE / "codeout"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{date.today().isoformat()}_{tag}.md"
    n = 1
    while f.exists():
        f = d / f"{date.today().isoformat()}_{tag}-{n}.md"
        n += 1
    f.write_text(text, encoding="utf-8")
    return f"codeout/{f.name}"


@register("code", "/code [python|bash|js|ts] <task…>   ·   /code debug <code + error>",
          "production-grade code (typed, tested, commented) + systematic debugging")
def code(ctx, arg: str) -> str:
    try:
        arg = arg.strip()
        if not arg:
            return "ERROR: /code [python|bash|js|ts] <task>  |  /code debug <code + error>"
        if arg.lower().startswith("debug"):
            payload = arg.split(None, 1)[1].strip() if len(arg) > 5 else ""
            if len(payload) < 20:
                return "ERROR: /code debug needs the code snippet + observed error (≥20 chars)"
            llm = _llm(ctx, "Systematically debug the code below. Output: '### Root cause' (one "
                            "sentence), '### Evidence' (which line/why, quoted), '### Fix' (one fenced "
                            "code block with the corrected code), '### Regression test' (one fenced "
                            "block). No prose before root cause.\n\n" + payload[:6000])
            text = llm or _debug_fallback(payload)
            return "_(saved → " + _save(text, "debug") + ")_\n\n" + text
        lang, task = _detect_lang(arg)
        llm = _llm(ctx, PROMPTS[lang] + f"\n\nTask: {task[:4000]}", max_tokens=1400)
        text = llm or _skeleton(lang, task)
        return "_(language: " + lang + " · saved → " + _save(text, lang) + ")_\n\n" + text
    except Exception as e:
        return f"ERROR: /code failed safely: {type(e).__name__}: {e}"
