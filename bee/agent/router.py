"""Hybrid routing — four tiers, fused heuristics + learned ML.

Tiers (in order of precedence):
  0. explicit   — user override (`cloud:` prefix, "use cloud/local", /model)
  1. det        — pure math expression → deterministic eval, NO LLM at all
  2. ml         — learned classifier (bee.brain.mlrouter), only if trained on
                  enough episodes and confident (shadow-logged always)
  3. heuristic  — complexity cues + length (the original rules)

route() returns a dict; route_task() keeps the legacy tuple API.
"""
from __future__ import annotations

import re
import time

from ..config import Config
from ..monitor import metrics

CLOUD_HINT = re.compile(r"\b(use cloud|cloud mode|deep reasoning|use llm cloud)\b", re.I)
LOCAL_HINT = re.compile(r"\b(use local|local model|local only|offline)\b", re.I)
CLOUD_PREFIX = re.compile(r"^\s*cloud:\s*", re.I)
# Local bee4b is text-only: image-bearing tasks need the multimodal cloud
# tier. Explicit LOCAL_HINT still wins (offline intent is a privacy choice —
# the loop then answers best-effort or fails honestly). "docker image" is
# excluded: a container reference, not a picture.
IMAGE_EXT = re.compile(r"\.(png|jpe?g|webp|gif|bmp|tiff?)\b", re.I)
IMAGE_WORDS = re.compile(
    r"\b(photo|picture|screenshot|selfie|image|painting|diagram|meme|camera"
    r"|take a photo|describe (this|the) image|what (is in|does) (this|the) (photo|picture|image))\b", re.I)
_DOCKER_IMAGE = re.compile(r"\bdocker\s+image\b", re.I)


def needs_vision(task: str) -> bool:
    """True when the task refers to an actual picture (not a docker image)."""
    t = task or ""
    if _DOCKER_IMAGE.search(t):
        return False
    return bool(IMAGE_EXT.search(t) or IMAGE_WORDS.search(t))

COMPLEX_CUES = [
    "architect", "design a system", "design a solution", "refactor", "audit",
    "comprehensive", "in depth", "in-depth", "long-form", "long form", "book",
    "research report", "deep analysis", "legal", "medical advice", "financial analysis",
    "prove", "theorem", "derivation", "thesis", "whitepaper", "proposal",
    "compare and recommend", "trade-offs", "multi-agent", "optimize the algorithm",
]
COMPLEX_LEN = 320
COMPLEX_STEPS = re.compile(r"\b(step\s+\d|phase\s+\d|first.*then.*then|1\.\s.*2\.\s.*3\.\s)\b", re.I | re.S)

_EXPR = re.compile(r"^[\d\s\+\-\*/%\.\(\),eE]+$")
# '%' only counts as an operator when it sits between digits (modulo), so a bare
# "100%" task still goes to the LLM instead of failing in the deterministic tier
_HAS_OP = re.compile(r"[+\-\*/]|\*\*|\d\s*%\s*\d")

# ------------------------------------------------- phrase-aware math extraction
# Small models are unreliable at arithmetic (a 3B model answered 17*23 = 401),
# so anything that IS math must never reach the LLM at all. This extractor turns
# pure expressions and lightly-phrased asks ("what is 17*23?", "calculate 10% of
# 200", "5 plus 5", "6 to the power of 2") into a safe arithmetic expression.
_LEAD = re.compile(
    r"^(?:what(?:'s|\s+is|\s+was)?|calculate|compute|evaluate|solve|work\s+out|"
    r"how\s+much\s+(?:is|are)|find\s+the\s+answer\s+to|find|answer\s+to|"
    r"give\s+me|tell\s+me|the\s+result\s+of|result\s+of|pls|please)\s+",
    re.I)
_TAIL = re.compile(
    r"\s+(?:for\s+me|now|today|please|step\s+by\s+step|thanks|thank\s*you|thx"
    r"|answer\s+(?:with\s+)?(?:just\s+|only\s+)?the\s+(?:number|answer|result)"
    r"|answer\s+only"
    r"|just\s+the\s+(?:number|answer|result)"
    r"|only\s+the\s+(?:number|answer|result)"
    r"|no\s+explanation"
    r"|and\s+one[-\s]?line\s+working"
    r"|show\s+(?:your|the)\s+(?:work|working)"
    r"|in\s+one\s+line"
    r")\b[.!?]*$",
    re.I)
_WORD_OPS = [
    (re.compile(r"\bmultiplied\s+by\b", re.I), "*"),
    (re.compile(r"\bdivided\s+by\b", re.I), "/"),
    (re.compile(r"\bto\s+the\s+power\s+of\b", re.I), "**"),
    (re.compile(r"\bplus\b", re.I), "+"),
    (re.compile(r"\bminus\b", re.I), "-"),
    (re.compile(r"\btimes\b", re.I), "*"),
    (re.compile(r"\bsquared\b", re.I), "**2"),
    (re.compile(r"\bcubed\b", re.I), "**3"),
]


def _strip_phrase(t: str) -> str:
    t = t.strip()
    changed = True
    while changed:
        changed = False
        s = _LEAD.sub("", t, count=1)
        if s != t:
            t, changed = s.strip(), True
        s = _TAIL.sub("", t, count=1)
        if s != t:
            t, changed = s.strip(), True
        s = t.strip(" .!?")
        if s != t:
            t, changed = s, True
    return t


def _normalize_expr(c: str) -> str:
    c = c.replace("^", "**")
    for rx, op in _WORD_OPS:
        c = rx.sub(op, c)
    c = re.sub(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+", r"\1/100*", c, flags=re.I)
    return re.sub(r"\s+", " ", c).strip()


# Words that frame a computation without being part of it. Stripped only AFTER
# expression normalization, and only when a compute intent verb is present, so
# any leftover prose makes the residue invalid and the task falls back to the
# model — the safe direction is always "don't answer".
# Deliberately excludes every name eval_safe allows (sum/min/max/len/sqrt/...)
# so a real expression is never gutted by the strip.
_MATH_INTENT = re.compile(
    r"\b(?:calculat\w*|compute|evaluat\w*|solve|what(?:'s|\s+(?:is|was|are))|"
    r"how\s+much\s+(?:is|are)|result\s+of|find\s+(?:the\s+)?(?:value|result|answer)|"
    r"work\s+out|evaluate)\b", re.I)
_MATH_NOISE = re.compile(
    r"\b(?:use|using|the|a|an|tool|tools|function|functions|calculator|calc|to|"
    r"given|below|following|expression|equation|then|than|give|tell|me|my|us|"
    r"report|returns?|provide|show|display|output|final|last|correct|right|"
    r"number|value|result|answer|equation|is|are|equal|equals|what|which|"
    r"and|or|of|it|that|this|these|those|with|without|for|as|in|on|at|by|"
    r"please|just|only|now|today|one|single|short|brief|line|step|steps|"
    r"working|solution|question|task)\b[\s:;,]*",
    re.I)
_HAS_NUM = re.compile(r"\d")


def _residue_is_math(c: str) -> bool:
    """True when the residue is arithmetic whose only names are math functions.

    The routing guard `_EXPR` deliberately allows digits/operators only (so prose
    can never match), which is too strict for `sqrt(144)`-style expressions that
    eval_safe DOES support. So the residue is validated structurally instead:
    parse it, reject anything but math names/calls/operators, and let eval_safe
    remain the execution guard.
    """
    import ast
    try:
        from ..tools.base import _ALLOWED_FUNCS
    except Exception:
        return False
    allowed = set(_ALLOWED_FUNCS)
    try:
        tree = ast.parse(c, mode="eval")
    except (SyntaxError, ValueError):
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.Attribute, ast.Lambda, ast.Starred, ast.NamedExpr,
                             ast.SetComp, ast.ListComp, ast.DictComp, ast.GeneratorExp)):
            return False
        if isinstance(node, ast.Constant) and not isinstance(node.value, (int, float, complex, bool)):
            return False
        if isinstance(node, ast.Name) and node.id not in allowed:
            return False
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed:
                return False
            if node.keywords:
                return False
        if isinstance(node, ast.JoinedStr) or isinstance(node, ast.FormattedValue):
            return False
    return True


def _embedded_expr(t: str) -> str | None:
    """Extract the arithmetic from a prose-wrapped ask: 'Use the calculator tool
    to compute 12 * 14 + 8 and give the final number.'

    A small model answers these inconsistently (it said 'none of the provided
    functions are for a calculator' and then computed the number itself), yet the
    value is fully determined — so it belongs to the deterministic tier.
    Conservative by construction: requires an intent verb, and the residue after
    stripping framing words must be pure math, else None (the model keeps the
    task). Any leftover prose — 'and email it to bob' — fails the residue test."""
    if not _MATH_INTENT.search(t):
        return None
    residue = _MATH_NOISE.sub(" ", t)
    residue = _MATH_INTENT.sub(" ", residue)          # the framing verb is noise too
    residue = re.sub(r"[\$\t]", " ", residue)
    residue = re.sub(r"\s+", " ", residue).strip(" .,;:!?-\t")
    if not residue or len(residue) > 120:
        return None
    c = _normalize_expr(residue)
    if not (c and _HAS_OP.search(c) and len(_HAS_NUM.findall(c)) >= 2):
        return None
    return c if _residue_is_math(c) else None


def math_expr(task: str) -> str | None:
    """Extract a safe arithmetic expression from pure or lightly-phrased math asks.

    Returns the normalized expression (Python syntax: `**` for power) or None.
    eval_safe (AST allow-list) is the final guard; this only decides ROUTING, so
    it stays conservative - numbers, operators, parens, and light phrasing only.
    Natural-language tasks never match.
    """
    t = (task or "").strip()
    if not t or len(t) > 200:
        return None
    t = (t.replace("×", "*").replace("÷", "/")
          .replace("−", "-").replace("–", "-")
          .replace("²", "**2").replace("³", "**3"))
    cands = [t]
    stripped = _strip_phrase(t)
    if stripped and stripped != t:
        cands.append(stripped)
    for cand in cands:
        c = _normalize_expr(cand)
        if c and _EXPR.match(c) and _HAS_OP.search(c):
            return c
    return _embedded_expr(t)

def strip_cloud_prefix(task: str) -> str:
    return CLOUD_PREFIX.sub("", task).strip()


# ---------------------------------------------------------------- smalltalk
# Instant canned replies for pure greetings/thanks — zero model calls, zero
# latency. Anything with substance still goes to the normal tiers.
SMALLTALK_RULES = [
    (re.compile(r"^(hi|hiya|hey|hello|yo|howdy|heyy+|hiii+|good\s*(morning|afternoon|evening|day))\b[\s!.,]*$", re.I),
     "Ready when you are. What do you need done?"),
    (re.compile(r"^(thanks|thank\s*you|thx|ty|cheers|appreciated)\b[\s!.,]*$", re.I),
     "Anytime. Anything else on the plate?"),
    (re.compile(r"^(bye|goodbye|see\s*ya|see\s*you|good\s*night|gn|cya)\b[\s!.,]*$", re.I),
     "Bye. I'll be here when you need me."),
    (re.compile(r"^(ok(ay)?|sure|cool|nice|great|awesome)\b[\s!.,]*$", re.I),
     "Understood. What's next?"),
]


def smalltalk(task: str) -> str | None:
    t = (task or "").strip()
    if len(t) > 30:
        return None
    for rx, reply in SMALLTALK_RULES:
        if rx.search(t):
            return reply
    return None


def _is_det(task: str) -> bool:
    return math_expr(task) is not None



def _heuristic(task: str, cfg: Config) -> str:
    t = task.strip()
    score = sum(1 for cue in COMPLEX_CUES if cue in t.lower())
    complex_flag = (score >= 2) or (len(t) > COMPLEX_LEN and score >= 1) or bool(COMPLEX_STEPS.search(t))
    if complex_flag and cfg.cloud.enabled and cfg.cloud.llm:
        return "cloud"
    return "local"


def route(task: str, cfg: Config, model: str | None = None) -> dict:
    t = (task or "").strip()
    # Deterministic math wins over EVERYTHING (including explicit engine
    # overrides): instant, free, and 100% correct — a model should never
    # be the calculator (a 3B model once answered 17*23 = 401).
    expr = math_expr(t)
    if expr is not None:
        return {"name": "det", "escalated": False, "source": "deterministic",
                "conf": 1.0, "expr": expr}
    if model:
        return {"name": model, "escalated": model == "cloud", "source": "explicit", "conf": 1.0}
    if CLOUD_PREFIX.search(t):
        return {"name": "cloud", "escalated": True, "source": "explicit", "conf": 1.0}
    if CLOUD_HINT.search(t):
        return {"name": "cloud", "escalated": True, "source": "explicit", "conf": 1.0}
    if LOCAL_HINT.search(t):
        return {"name": "local", "escalated": False, "source": "explicit", "conf": 1.0}
    if needs_vision(t) and cfg.cloud.enabled and cfg.cloud.llm:
        return {"name": "cloud", "escalated": True, "source": "vision", "conf": 1.0}
    st = smalltalk(t)
    if st is not None:
        return {"name": "smalltalk", "escalated": False, "source": "deterministic",
                "conf": 1.0, "smalltalk_reply": st}
    # ML tier (learned from episodes; shadow-logged even when heuristics win).
    # OPTIONAL OPTIMIZER (Phase 7): the deterministic tiers above already ran;
    # if ML is absent/broken the heuristic below simply decides. ML may also
    # escalate (complexity floor) but never demote a structurally complex task.
    heur = _heuristic(t, cfg)
    ml = None
    ml_ms = 0.0
    if cfg.router.ml_enabled:
        from ..brain import mlrouter
        t0 = time.time()
        try:
            ml = mlrouter.predict(t, min_conf=cfg.router.ml_confidence)
        except Exception:
            ml = None
        ml_ms = round((time.time() - t0) * 1000, 1)
    if ml:
        label, conf = ml
        name = "cloud" if label == "cloud" else ("det" if label == "det" else "local")
        if name == "det" and not _is_det(t):
            name = "local"  # never send natural language to the calculator
        if name == "cloud" and not (cfg.cloud.enabled and cfg.cloud.llm):
            name = "local"  # no cloud available
        source = "ml"
        if name == "local" and heur == "cloud":
            # complexity floor: ML may escalate, but never demote a
            # structurally complex task to the 3B local model
            name, conf, source = "cloud", 0.9, "complexity"
        metrics.record("route_ml", pred=label, conf=conf, used=True,
                       source=source, ms=ml_ms)
        return {"name": name, "escalated": name == "cloud", "source": source, "conf": conf}

    if ml is None and cfg.router.ml_enabled:
        # Phase 7 telemetry: record WHY the optimizer fell back (not_trained /
        # load_failed:<clear message> / low_confidence) — this is what the
        # runtime report's fallback-rate is computed from.
        from ..brain import mlrouter
        try:
            st = mlrouter.load_status()
            if st.get("exists"):
                reason = ("low_confidence" if st.get("loaded")
                          else f"load_failed: {str(st.get('error') or '')[:80]}")
            else:
                reason = "not_trained"
        except Exception:
            reason = "unknown"
        metrics.record("route_ml_fallback", reason=reason, ms=ml_ms)
        metrics.record("route_ml", pred="unavailable", used=False, ms=ml_ms)
    return {"name": heur, "escalated": heur == "cloud", "source": "heuristic", "conf": 0.5}


def route_task(task: str, cfg: Config, model: str | None = None) -> tuple[str, bool]:
    r = route(task, cfg, model)
    return r["name"], r["escalated"]
