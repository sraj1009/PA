"""Static contract: an in-project call must match the signature it targets.

Why this exists (docs/TECHNICAL_DEBT.md A27a, A37a): `_Semantic.search` called
`rag.retrieve(query, k=)` against `retrieve(ctx, query, k)`, and `chat_stream`
called `_ollama_stream(info, kwargs, on_token, tok, emitted)` against a signature
that also takes `tools`. Both raised `TypeError` inside a blanket
`except Exception`, so the feature just returned nothing / failed as a generic
provider error, and a green 700-test suite certified both as working. An argument
list that cannot bind is a machine-checkable fact, so it is checked here instead
of being discovered by a user.

Scope deliberately conservative: only calls whose target is resolved with
confidence (same-module function, `ClassName.method`, `var.method` where `var =
ClassName(...)` is visible in the same function, and `self/cls.method` inside the
enclosing class including one level of in-project base). `*args`/`**kwargs` calls
and `**kwargs`-accepting targets are skipped. Names colliding across modules are
resolved per module, so `EventBus.subscribe` cannot be confused with the kernel
facade's.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

BEE_DIR = Path(__file__).resolve().parent.parent / "bee"


class _Sig:
    def __init__(self, node: ast.AST, cls: str | None):
        a = node.args
        self.name = node.name
        self.cls = cls
        self.params = [n.arg for n in list(getattr(a, "posonlyargs", []) or []) + list(a.args)]
        self.kwonly = [n.arg for n in a.kwonlyargs]
        self.req_kwonly = [n.arg for n, d in zip(a.kwonlyargs, a.kw_defaults) if d is None]
        self.vararg = a.vararg.arg if a.vararg else None
        self.kwarg = a.kwarg.arg if a.kwarg else None
        decs = {(getattr(d, "id", None) or getattr(d, "attr", "")) for d in node.decorator_list}
        self.static = "staticmethod" in decs
        self.clsmeth = "classmethod" in decs
        self.bound = (cls is not None and bool(self.params)
                      and self.params[0] in ("self", "cls") and not self.static)
        self.required = len(self.params) - len(a.defaults)


def _collect():
    modules = {}
    for dirpath, dirnames, filenames in os.walk(BEE_DIR):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for f in filenames:
            if f.endswith(".py"):
                p = Path(dirpath) / f
                modules[p.relative_to(BEE_DIR.parent).as_posix()] = ast.parse(
                    p.read_text(encoding="utf-8"))
    funcs, methods, classes = {}, {}, {}
    for mod, tree in modules.items():
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs[(mod, node.name)] = _Sig(node, None)
            elif isinstance(node, ast.ClassDef):
                _collect_class(mod, node, methods, classes)
    return modules, funcs, methods, classes


def _collect_class(mod, node, methods, classes):
    classes.setdefault((mod, node.name), set()).update(
        (b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")) for b in node.bases)
    classes.setdefault((None, node.name), set()).update(
        (b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")) for b in node.bases)
    for sub in node.body:
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
            methods[(mod, node.name, sub.name)] = _Sig(sub, node.name)
        elif isinstance(sub, ast.ClassDef):
            _collect_class(mod, sub, methods, classes)


def _mismatch(sig: _Sig, call: ast.Call, unbound: bool) -> str | None:
    if any(k.arg is None for k in call.keywords) or any(isinstance(a, ast.Starred) for a in call.args):
        return None                      # *a / **kw: cannot judge statically
    if sig.static:
        off = 0
    elif sig.clsmeth and unbound:
        off = 1                          # Cls.factory(x): cls comes from the receiver
    elif sig.bound and not unbound:
        off = 1                          # instance.method(x)
    else:
        off = 0
    pos = sig.params[off:]
    req = max(0, sig.required - off)          # `self`/`cls` is not an argument to supply
    npos = len(call.args)
    kwargs = [k.arg for k in call.keywords if k.arg]
    if not sig.vararg and npos > len(pos):
        return f"{sig.name}() accepts {len(pos)} positional ({', '.join(pos)}), call passes {npos}"
    missing = [p for p in pos[npos:req] if p not in kwargs]
    if missing:
        return f"{sig.name}() missing required argument(s) {missing}"
    if not sig.kwarg:
        bad = [k for k in kwargs if k not in pos and k not in sig.kwonly]
        if bad:
            return (f"{sig.name}() got unexpected keyword(s) {bad}; signature is "
                    f"({', '.join(pos)}{', kw-only: ' + ', '.join(sig.kwonly) if sig.kwonly else ''})")
        clash = [k for k in kwargs if k in pos[:npos]]
        if clash:
            return f"{sig.name}() got multiple values for {clash}"
    if not sig.kwarg:
        km = [k for k in sig.req_kwonly if k not in kwargs]
        if km:
            return f"{sig.name}() missing required keyword-only argument(s) {km}"
    return None


def _function_contexts(tree):
    """For each function node: its enclosing class (if direct) and `var -> Class` map."""
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            infer = {}
            for sub in ast.walk(node):
                if (isinstance(sub, ast.Assign) and len(sub.targets) == 1
                        and isinstance(sub.targets[0], ast.Name)
                        and isinstance(sub.value, ast.Call)
                        and isinstance(sub.value.func, ast.Name)):
                    infer[sub.targets[0].id] = sub.value.func.id
            out[id(node)] = (None, infer)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    out[id(sub)] = (node.name, out[id(sub)][1])
    return out


def _walk_calls(tree):
    """Yield (call, enclosing_function) for every call, including module level."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            for call in ast.walk(node):
                if isinstance(call, ast.Call):
                    yield call, node


def _lookup_method(mod, cls, name, classes, methods, seen=None):
    """Resolve `cls.name` in `mod`, walking in-project bases once each."""
    seen = seen or set()
    sig = methods.get((mod, cls, name))
    if sig:
        return sig
    for base in classes.get((mod, cls), ()) or classes.get((None, cls), ()):
        if base in seen:
            continue
        seen.add(base)
        for m in classes:
            if m[1] == base:
                sig = _lookup_method(m[0], base, name, classes, methods, seen)
                if sig:
                    return sig
    return None


def find_mismatches():
    modules, funcs, methods, classes = _collect()
    class_names = {c for (_m, c) in classes}
    bad = []
    for mod, tree in modules.items():
        ctxs = _function_contexts(tree)
        for call, fn in _walk_calls(tree):
            encl, infer = ctxs.get(id(fn), (None, {}))
            f = call.func
            sig, unbound = None, False
            if isinstance(f, ast.Name):
                sig = funcs.get((mod, f.id))
            elif isinstance(f, ast.Attribute):
                if isinstance(f.value, ast.Name):
                    recv = f.value.id
                    if recv in class_names:
                        # Cls.method(...) — an explicit receiver argument is expected
                        sig = _lookup_method(mod, recv, f.attr, classes, methods)
                        unbound = bool(sig) and not (sig.static or sig.clsmeth)
                    elif recv in infer:
                        sig = _lookup_method(mod, infer[recv], f.attr, classes, methods)
                    elif recv in ("self", "cls") and encl:
                        sig = _lookup_method(mod, encl, f.attr, classes, methods)
                elif isinstance(f.value, ast.Call) and isinstance(f.value.func, ast.Name) \
                        and f.value.func.id in class_names:
                    sig = _lookup_method(mod, f.value.func.id, f.attr, classes, methods)
            if sig is None:
                continue
            msg = _mismatch(sig, call, unbound)
            if msg:
                bad.append(f"{mod}:{call.lineno}: {msg}")
    return sorted(set(bad))


def test_no_in_project_call_mismatch():
    """A37e: the A27a/A37a defect class must fail CI, not hide behind an except."""
    assert find_mismatches() == []


def test_the_checker_actually_detects_the_original_defect():
    """A guard that can never fire is worse than none (see A16: spaced needle,
    stripped haystack). Feed the checker the exact bug it exists to catch."""
    src = """
def retrieve(ctx, query, k=5):
    return ctx

def caller(query):
    return retrieve(query, k=3)
"""
    tree = ast.parse(src)
    sig = _Sig(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "retrieve"), None)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "retrieve")
    msg = _mismatch(sig, call, unbound=False)
    assert msg and "missing required argument" in msg, msg


def test_the_checker_actually_detects_the_streaming_defect():
    """The A37a call verbatim: `tools` omitted, so the LAST positional is the one
    Python reports as missing — the real live error said exactly this."""
    src = """
class LLMClient:
    def _ollama_stream(self, info, kwargs, tools, on_token, tok, emitted):
        return None
    def chat_stream(self, info, kwargs, on_token, tok, emitted):
        return self._ollama_stream(info, kwargs, on_token, tok, emitted)
"""
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    sig = _Sig(next(m for m in cls.body if getattr(m, "name", "") == "_ollama_stream"), "LLMClient")
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and getattr(n.func, "attr", "") == "_ollama_stream")
    msg = _mismatch(sig, call, unbound=False)
    assert msg and "emitted" in msg, msg


def test_the_checker_actually_detects_the_wrong_keyword_defect():
    """A27a was the other half: the query went to the `ctx` parameter and a `k=`
    keyword the target does not accept. An unexpected keyword must be caught too."""
    src = """
def retrieve(ctx, query, k=5):
    return ctx

def caller(ctx, query):
    return retrieve(ctx, query, num_k=3)
"""
    tree = ast.parse(src)
    sig = _Sig(next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "retrieve"), None)
    call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                and getattr(n.func, "id", "") == "retrieve")
    msg = _mismatch(sig, call, unbound=False)
    assert msg and "num_k" in msg, msg
