"""Fast paths — pure-Python handlers for the most common user asks.

Matched right after smalltalk/math, BEFORE any LLM call. Everything here is
deterministic, offline where possible, and answers in milliseconds:

    time · date · uptime · weather [city] · unit conversions · coin/dice/random
    open <app> · open <file> · search/google <q> · note <text> · todo <text>
    wikipedia <topic> · play/youtube <q> · media pause/resume/next/prev
    PC control: volume · battery · lock · sleep · brightness · show desktop
    Welcome Home protocol · take a photo (optional vision)
    RAM/CPU/battery stats · public IP · identity · help · "what's on my plate" · speak

Safety: fast paths that touch the system (open app, search, open file) return
a FastExec and are executed through the SAME guard as LLM tool calls — a fast
path can never bypass permissions. Handlers may return None to decline (then
the normal model pipeline runs instead — e.g. weather with no internet).

Adding one (5 lines):
    def _time(ctx, m):
        from datetime import datetime
        return f"It's {datetime.now():%H:%M}."
    FASTPATHS.append(FastPath("time", re.compile(r"^...$"), _time))
"""
from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Optional, Pattern


@dataclass
class FastPath:
    name: str
    rx: Pattern
    handle: Callable  # (ctx, match) -> str | FastExec | None   (None = fall through)
    # Utterance-length ceiling. The global 120-char cap exists so a long paragraph
    # of prose cannot accidentally match a spoken command; a path that expects the
    # user to paste content (code) needs more, and says so per path instead of
    # loosening the cap for everything.
    max_len: int = 120


@dataclass
class FastExec:
    """A fast path that needs ONE tool call — runs under the guard."""
    tool: str
    args: dict
    reply: Callable | str                 # (tool_result) -> final markdown
    blocked: Callable | str = "Guard blocked the action."  # (reason) -> final markdown


# ------------------------------------------------------------------ helpers
def _cim(powershell_expr: str) -> str:
    """Run one small PowerShell query. '' on any failure (handler declines)."""
    import subprocess
    import sys
    if sys.platform != "win32":
        return ""
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", powershell_expr],
                           capture_output=True, text=True, timeout=12)
        return (r.stdout or "").strip()
    except Exception:
        return ""


def _http_text(url: str, timeout: float = 6.0, params: dict | None = None) -> str:
    try:
        import httpx
        r = httpx.get(url, timeout=timeout, params=params, headers={"User-Agent": "bee/1.0"})
        if r.status_code == 200:
            return r.text.strip()
    except Exception:
        pass
    return ""


# ------------------------------------------------------------------ handlers
def _time(ctx, m):
    from datetime import datetime
    now = datetime.now()
    return f"It's {now:%H:%M} on {now:%A, %d %B %Y}."


def _date(ctx, m):
    from datetime import datetime
    now = datetime.now()
    return f"Today is {now:%A, %d %B %Y} — {now:%H:%M}."


def _uptime(ctx, m):
    out = _cim("(Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('yyyy-MM-dd HH:mm')")
    if not re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$", out):
        return None
    from datetime import datetime
    boot = datetime.strptime(out, "%Y-%m-%d %H:%M")
    d = datetime.now() - boot
    return f"PC booted {boot:%d %b %Y %H:%M} — up {d.days}d {d.seconds // 3600}h {(d.seconds // 60) % 60}m."


def _weather(ctx, m):
    city = (m.group(2) or "").strip() or "current location"
    txt = _http_text(f"https://wttr.in/{urllib.parse.quote(city)}", params={"format": "3"})
    if not txt:
        return None  # offline — let the model (with web tool) handle it
    return f"**{city}**: {txt}"


_LEN = {"km": 1000, "kilometre": 1000, "kilometer": 1000, "m": 1, "meter": 1, "metre": 1,
        "cm": 0.01, "mm": 0.001, "mile": 1609.344, "miles": 1609.344,
        "inch": 0.0254, "inches": 0.0254, "in": 0.0254,
        "ft": 0.3048, "feet": 0.3048, "foot": 0.3048, "yard": 0.9144, "yards": 0.9144}
_MASS = {"kg": 1, "kilogram": 1, "kilograms": 1, "g": 0.001, "gram": 0.001, "grams": 0.001,
         "pound": 0.45359237, "pounds": 0.45359237, "lb": 0.45359237, "lbs": 0.45359237}
_DATA = {"kb": 1024.0, "mb": 1048576.0, "gb": 1073741824.0, "tb": 1099511627776.0}


def _convert(ctx, m):
    val = float(m.group(1).replace(",", ""))
    src, dst = m.group(2).lower(), m.group(3).lower()
    for dim in (_LEN, _MASS, _DATA):
        if src in dim and dst in dim:
            out = val * dim[src] / dim[dst]
            return f"{m.group(1)} {src} = **{out:,.6g} {dst}**"
    if src in ("celsius", "°c", "c") and dst in ("fahrenheit", "°f", "f"):
        return f"{val}°C = **{val * 9 / 5 + 32:,.6g}°F**"
    if src in ("fahrenheit", "°f", "f") and dst in ("celsius", "°c", "c"):
        return f"{val}°F = **{(val - 32) * 5 / 9:,.6g}°C**"
    return None


def _coin(ctx, m):
    import random
    return f"**{random.choice(['heads', 'tails']).capitalize()}**."


def _dice(ctx, m):
    import random
    return f"**{random.randint(1, 6)}**"


def _random_between(ctx, m):
    import random
    lo, hi = int(m.group(1)), int(m.group(2))
    if hi < lo:
        lo, hi = hi, lo
    return f"**{random.randint(lo, hi)}**"


def _pick(ctx, m):
    import random
    opts = [o.strip() for o in m.group(1).split(",") if o.strip()]
    if len(opts) < 2:
        return None
    return f"**{random.choice(opts)}** (picked from {len(opts)} options)"


APPS = {
    "chrome": "chrome", "google chrome": "chrome",
    "edge": "msedge", "microsoft edge": "msedge",
    "notepad": "notepad", "word": "winword", "excel": "excel",
    "powerpoint": "powerpnt", "outlook": "outlook", "mail": "outlook",
    "explorer": "explorer", "file explorer": "explorer", "this pc": "explorer",
    "cmd": "cmd", "terminal": "powershell", "powershell": "powershell",
    "paint": "mspaint", "calculator": "calc", "vscode": "code", "code": "code",
    "spotify": "spotify", "discord": "discord", "slack": "slack", "zoom": "zoom",
    "task manager": "taskmgr", "settings": "ms-settings:",
    "camera": "shell:AppsFolder\\microsoft.windows.camera_8wekyb3d8bbwe!App",
    "photos": "shell:AppsFolder\\microsoft.windows.photos_8wekyb3d8bbwe!App",
    "store": "ms-windows-store://default", "microsoft store": "ms-windows-store://default",
    "maps": "https://www.google.com/maps", "whatsapp": "https://web.whatsapp.com",
    "telegram": "https://web.telegram.org", "gmail": "https://mail.google.com",
    "youtube": "https://www.youtube.com", "yt": "https://www.youtube.com",
    "grok": "https://grok.com", "accio": "accio",
}


def _open_app(ctx, m):
    app = m.group(1).lower()
    target = APPS.get(app)
    if not target:
        return None
    if target.startswith("http"):
        return _open_url(ctx, target, f"Opened **{app}** in your browser.")
    return FastExec(
        "shell", {"command": f"start {target}"},
        reply=lambda r: (f"Opened **{app}**."
                         if not (isinstance(r, dict) and r.get("error"))
                         else f"Could not open {app}: {r.get('error')} - is it installed?"),
        blocked=lambda reason: f"\u26a0 Guard blocked launching {app} ({reason}). Command was NOT run.",
    )


def _open_profile(ctx, m):
    browser, n = m.group(1).lower(), int(m.group(2))
    exe = "chrome" if "chrom" in browser else "msedge"
    return FastExec(
        "shell", {"command": f'start {exe} --profile-directory="Profile {n}"'},
        reply=lambda r: (f"Opened **{browser}** with user/profile {n}."
                         if not (isinstance(r, dict) and r.get("error"))
                         else f"Could not open {browser} profile {n}: {r.get('error')}"),
        blocked=lambda reason: f"\u26a0 Guard blocked launching {browser} ({reason}).",
    )


def _open_inverted(ctx, m):
    app = m.group(1).lower()
    target = APPS.get(app)
    if not target:
        return None
    if target.startswith("http"):
        return _open_url(ctx, target, f"Launched **{app}** in your browser.")
    return FastExec(
        "shell", {"command": f"start {target}"},
        reply=lambda r: (f"Launched **{app}**."
                         if not (isinstance(r, dict) and r.get("error"))
                         else f"Could not launch {app}: {r.get('error')} - is it installed?"),
        blocked=lambda reason: f"\u26a0 Guard blocked launching {app} ({reason}).",
    )


def _open_domain(ctx, m):
    raw = m.group(1).strip().rstrip(".?!")
    if raw.startswith(("http://", "https://")):
        url = raw
    elif re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+[a-z0-9/._%?&=#-]*$", raw, re.I):
        url = "https://" + raw
    else:
        return None
    return _open_url(ctx, url, f"Opened **{raw}** in your browser.")


def _open_file(ctx, m):
    name = m.group(1)
    from pathlib import Path
    p = (Path(ctx.workspace) / name).resolve()
    if not str(p).startswith(str(Path(ctx.workspace).resolve())) or not p.exists():
        return None
    return FastExec(
        "shell", {"command": f'start "" "{p}"'},
        reply=lambda r: f"Opened **{p.name}**." if not (isinstance(r, dict) and r.get("error"))
                        else f"Could not open {p.name}: {r.get('error')}",
        blocked=lambda reason: f"⚠ Guard blocked opening {p.name} ({reason}).",
    )


def _search(ctx, m):
    q = m.group(1).strip()
    url = "https://www.google.com/search?q=" + urllib.parse.quote(q)
    return FastExec(
        "shell", {"command": f'start "" "{url}"'},
        reply=lambda r: f"Searching: **{q}**" if not (isinstance(r, dict) and r.get("error"))
                        else f"Could not open the browser ({r.get('error')}). Try directly: {url}",
        blocked=lambda reason: f"⚠ Guard blocked the browser launch ({reason}). Try directly: {url}",
    )


def _note(ctx, m):
    text = m.group(1).strip()
    from ..memory.md import diary_add
    diary_add(f"note (fast path): {text}")
    return f"Noted — saved to today's diary: {text}"


def _todo(ctx, m):
    from .. import commands as _cmds
    out = _cmds.get("plan").handler(ctx, "add " + m.group(1).strip())
    if out is None or out.startswith("ERROR"):
        return None
    return out


_REMIND_LEAD = re.compile(r"^(?:to\s+|that\s+|about\s+|the\s+fact\s+that\s+)", re.I)


def _remind_cmd(ctx, body: str):
    """One implementation for both surfaces: the spoken fast path and /remind
    share the parser, the durable job shape and the delivery, so a reminder set
    by voice is listed and cancelled by the slash command and vice versa."""
    from .. import commands as _cmds
    cmd = _cmds.get("remind")
    if cmd is None:
        return None
    out = cmd.handler(ctx, body)
    # ERROR (no worker / no time in the words) declines instead of answering, so
    # the model gets the turn rather than the user getting a usage message.
    if out is None or out.startswith("ERROR"):
        return None
    return out


def _remind(ctx, m):
    body = _REMIND_LEAD.sub("", (m.group(1) or "").strip())
    if not body:
        return None
    return _remind_cmd(ctx, body)


def _remind_list(ctx, m):
    return _remind_cmd(ctx, "list")


def _remind_cancel(ctx, what: str):
    return _remind_cmd(ctx, f"cancel {what}")


def _files_list_reply(r) -> str:
    if not isinstance(r, dict):
        return "Could not read that folder."
    if r.get("error"):
        return f"Could not list it: {r['error']}"
    entries = [e for e in (r.get("entries") or []) if "\t" in e]
    dirs = [e.split("\t")[1] for e in entries if e.startswith("d\t")]
    files = [e.split("\t")[1] for e in entries if e.startswith("f\t")]
    head = (f"**{r.get('path', '.')}** — {len(dirs)} "
            f"{'directory' if len(dirs) == 1 else 'directories'}, "
            f"{len(files)} {'file' if len(files) == 1 else 'files'}")
    lines = [head]
    if dirs:
        lines.append("- folders: " + ", ".join(dirs[:60]))
    if files:
        lines.append("- files: " + ", ".join(files[:60]))
    if any(e.startswith("...") for e in r.get("entries") or []):
        lines.append("_truncated at 300 entries_")
    return "\n".join(lines)


_FILES_HEAD = re.compile(
    r"^(?:please\s+)?(?:"
    r"(?:list|show(?:\s+me)?)\s+(?:the\s+|all\s+|top[- ]level\s+|its\s+)*"
    r"(?:files?|folders?|directories|entries|contents)\b"
    r"|(?:what|how\s+many)\s+(?:are\s+)?(?:the\s+|top[- ]level\s+)*"
    r"(?:files?|folders?|directories|entries)\b"
    r"|what(?:'s|s|\s+is|\s+are)?\s+in\b"
    r")", re.I)
_FILES_NOUN = re.compile(r"\b(?:file|files|folder|folders|director(?:y|ies)|"
                         r"entries|contents|workspace|repo|root)\b", re.I)
_FILES_TARGET = re.compile(r"(?:\bin\s+|\bof\s+|\bunder\s+|\bat\s+)"
                           r"(?:the\s+|my\s+|our\s+)?"
                           r"(?P<t>[\w.][\w./\\-]{0,60})", re.I)


def _files_list(ctx, m):
    """"What files are in the workspace?" — the real tool, under the guard.

    The eval showed the local 3B model answering this with "I don't have access to
    file system operations in this environment" while `file_list` sat in its tool
    list: with 30 schemas offered it sometimes declines outright. Listing a folder
    is deterministic work, so it must not depend on the model noticing."""
    text = m.string or ""
    target = ""
    tm = _FILES_TARGET.search(text)
    if tm:
        target = tm.group("t").strip().strip("/\\.,;:!?")
    # The bare "what's in …" form is ambiguous ("what is in the oven"). Only take
    # it when the sentence is actually about folders; otherwise decline and let
    # the model answer.
    if not _FILES_NOUN.search(text) and not re.search(r"[/\\]|\.\.", target):
        return None
    if (not target or target.lower()
            in ("workspace", "here", "root", "project", "folder", "directory",
                "current", "this", "the", "it", "that")):
        target = "."
    return FastExec(
        tool="file_list", args={"path": target},
        reply=_files_list_reply,
        blocked=lambda reason: f"⚠ Listing that folder was not allowed ({reason}).",
    )


def _specs(ctx, m):
    from ..tools import systemctl
    h = systemctl.get_hardware()
    if h is None:
        return None      # non-Windows / CIM failed — model pipeline takes over
    return "This machine — " + systemctl.format_hardware(h)


def _run_code(ctx, m):
    """Run code the user pasted, instead of hoping the model calls a tool.

    Two eval tasks say `Run python: <snippet>` and the 3B model replied by WRITING
    code (with a typo in the module name), or by burning 15 tool calls on variants —
    so the pasted snippet never ran. When the request contains the code, executing
    it is deterministic and needs no model judgement at all."""
    code = (m.group("c") or "").strip()
    code = re.sub(r"^```(?:python|py)?\s*", "", code, flags=re.I)
    code = re.sub(r"\s*```$", "", code).strip()
    # 'Run python: <snippet> — list which sorts are correct' is how the request
    # actually arrives: the trailing instruction is prose, not code, and leaving it
    # in the snippet produced a SyntaxError on the first live run. Python source
    # almost never carries a spaced em-dash, so cutting at the first one is safe.
    code = re.split(r"\s[—–]\s", code, maxsplit=1)[0].strip()
    if not code or len(code) > 4000:
        return None
    return FastExec(
        tool="code_run", args={"code": code},
        reply=_run_code_reply,
        blocked=lambda reason: ("⚠ Running that was not allowed "
                                f"({reason}). Nothing executed."),
    )


def _run_code_reply(r) -> str:
    if not isinstance(r, dict):
        return "The snippet did not run and returned nothing."
    if r.get("error"):
        return f"The snippet did not run: {r['error']}"
    out = str(r.get("output") or "").strip()
    err = str(r.get("error") or r.get("stderr") or "").strip()
    code = r.get("exit_code")
    if code not in (0, None):
        return (f"Exit **{code}**" + (f"\n```\n{err[:1500]}\n```" if err else "")
                + ((f"\noutput before the error:\n```\n{out[:1500]}\n```") if out else "")
                + "\n\nNothing I can report as a result — the snippet failed.")
    if not out:
        return "Ran with exit 0 and printed nothing."
    return out[:3000]


def _sysstats(ctx, m):
    from ..tools import systemctl
    s = systemctl.get_system_stats()
    if s is None:
        return None  # non-Windows / CIM failed — model pipeline takes over
    parts = [f"CPU **{s['cpu_pct']}%**",
             f"RAM free **{s['ram_free_mb']:,} MB** ({s['ram_pct']}% used)"]
    if s["battery_pct"] is not None:
        parts.append(f"Battery **{s['battery_pct']}%**")
    parts.append(f"C: drive free **{s['disk_free_gb']} GB**")
    return "System status — " + " · ".join(parts)


def _battery(ctx, m):
    from ..tools import systemctl
    b = systemctl.get_battery()
    if b is None:
        return "No battery detected — desktop / AC power."
    pct, ac = b
    state = {1: "plugged in", 0: "on battery"}.get(ac, "AC status unknown")
    low = " (low!)" if pct <= 20 else ""
    return f"Battery: **{pct}%** — {state}.{low}"


def _wikipedia(ctx, m):
    topic = m.group(1).strip().strip("?!.")
    if len(topic) < 3 or len(topic) > 80:
        return None
    try:
        import httpx
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + urllib.parse.quote(topic.replace(" ", "_"))
        r = httpx.get(url, timeout=6, headers={"User-Agent": "bee/1.0"})
        if r.status_code != 200:
            return None
        j = r.json()
        if j.get("type") in ("disambiguation", "special") or not j.get("extract"):
            return None
        page = ((j.get("content_urls") or {}).get("desktop") or {}).get("page", "")
        link = f"\n\n[Read more on Wikipedia]({page})" if page else ""
        return f"**{j.get('title', topic)}**\n\n{j['extract']}{link}"
    except Exception:
        return None  # offline / no page — model pipeline (with web tool) handles it


def _open_url(ctx, url: str, what: str):
    return FastExec(
        "shell", {"command": f'start "" "{url}"'},
        reply=lambda r: f"{what}" if not (isinstance(r, dict) and r.get("error"))
                        else f"Could not open the browser ({r.get('error')}). Try directly: {url}",
        blocked=lambda reason: f"⚠ Guard blocked the browser launch ({reason}). Try directly: {url}",
    )


def _play(ctx, m):
    q = m.group(1).strip()
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(q)
    return _open_url(ctx, url, f"▶ Searching YouTube for **{q}** — pick the first result (Spotify API can also be wired up later).")


def _media_factory(kind: str):
    action = {"pause": "playpause", "resume": "playpause", "next": "next", "prev": "prev"}[kind]
    verb = {"pause": "Pausing", "resume": "Resuming", "next": "Skipping to next track —",
            "prev": "Going back to previous track —"}[kind]

    def h(ctx, m):
        return FastExec(
            "systemctl", {"action": "media", "value": action},
            reply=lambda r: f"{verb} system media key sent."
                            if not (isinstance(r, dict) and r.get("error"))
                            else f"Media control failed: {r.get('error')}",
            blocked=lambda reason: f"⚠ Guard blocked media control ({reason}).",
        )
    return h


def _volume(ctx, m):
    raw = (m.group(1) or "up").lower()
    if raw in ("up", "increase", "raise", "louder", "higher"):
        val, msg = "up", "Volume up."
    elif raw in ("down", "decrease", "lower", "quieter"):
        val, msg = "down", "Volume down."
    elif raw.startswith("max"):
        val, msg = "max", "Volume to maximum."
    elif raw.startswith("unmute"):
        val, msg = "unmute", "Unmuted."
    elif "mute" in raw:
        val, msg = "mute", "Muted."
    else:
        return None
    return FastExec(
        "systemctl", {"action": "volume", "value": val},
        reply=lambda r: msg if not (isinstance(r, dict) and r.get("error"))
                        else f"Volume control failed: {r.get('error')}",
        blocked=lambda reason: f"⚠ Guard blocked the volume change ({reason}).",
    )


def _lock(ctx, m):
    return FastExec(
        "systemctl", {"action": "lock", "value": ""},
        reply=lambda r: "PC locked." if not (isinstance(r, dict) and r.get("error"))
                        else f"Lock failed: {r.get('error')}",
        blocked=lambda reason: f"⚠ Guard blocked the lock action ({reason}).",
    )


def _sleep(ctx, m):
    return FastExec(
        "systemctl", {"action": "sleep", "value": ""},
        reply=lambda r: "PC is going to sleep — see you when you wake it."
                        if not (isinstance(r, dict) and r.get("error"))
                        else f"Sleep failed: {r.get('error')}",
        blocked=lambda reason: f"⚠ Guard blocked putting the PC to sleep ({reason}).",
    )


def _brightness(ctx, m):
    level = int(m.group(1))
    if level > 100:
        return None
    return FastExec(
        "systemctl", {"action": "brightness", "value": str(level)},
        reply=lambda r: f"Brightness set to **{level}%**."
                        if not (isinstance(r, dict) and r.get("error"))
                        else f"Brightness control: {r.get('error')}",
        blocked=lambda reason: f"⚠ Guard blocked the brightness change ({reason}).",
    )


def _show_desktop(ctx, m):
    return FastExec(
        "systemctl", {"action": "show_desktop", "value": ""},
        reply=lambda r: "Desktop shown (all windows minimized)."
                        if not (isinstance(r, dict) and r.get("error"))
                        else f"Show-desktop failed: {r.get('error')}",
        blocked=lambda reason: f"⚠ Guard blocked show-desktop ({reason}).",
    )


def _welcome(ctx, m):
    from .. import commands
    out = commands.get("welcome").handler(ctx, "")
    return out or "Welcome protocol unavailable."


def _photo(ctx, m):
    try:
        import cv2
    except ImportError:
        return ("Vision module not installed — run `pip install -r requirements-vision.txt` "
                "to enable 'take a photo' + face detection.")
    try:
        import time as _t
        from pathlib import Path
        cap = cv2.VideoCapture(0)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            return "No webcam responded — check that the camera is connected and not in use."
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml"))
        faces = cascade.detectMultiScale(gray, 1.1, 5)
        snap_dir = Path(ctx.workspace) / "snapshots"
        snap_dir.mkdir(exist_ok=True)
        p = snap_dir / f"snap-{_t.strftime('%Y%m%d-%H%M%S')}.jpg"
        cv2.imwrite(str(p), frame)
        who = f" — {len(faces)} face(s) detected." if len(faces) else ""
        return f"Saved [snapshot]({p.name}){who}"
    except Exception as e:
        return f"Photo failed: {e}"


def _public_ip(ctx, m):
    ip = _http_text("https://api.ipify.org", timeout=6)
    if not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", ip):
        return None
    return f"Public IP: **{ip}**"


def _identity(ctx, m):
    return ("I'm BEE — your local-first executive & personal assistant: local bee4b (Qwen2.5-3B) "
            "with cloud escalation, guard rails on, everything on this machine. /help for commands.")


def _creator(ctx, m):
    u = getattr(ctx.cfg, "user", None)
    name = u.name if u else "my human"
    return (f"You did - **{name}** created me. BEE was built by {name} on this machine "
            f"(local-first, self-improving, hybrid local+cloud). I get sharper with every task.")


def _plate(ctx, m):
    from .. import commands as _cmds
    out = _cmds.get("plan").handler(ctx, "list")
    return out or "No open tasks yet — `/plan add <title>` to start."


def _help(ctx, m):
    return ("Quick map — instant answers: time, date, 'open <app>', 'search <q>', weather, "
            "'wikipedia <topic>', 'play <song>', unit conversions, 'note <x>', 'todo <x>', "
            "PC control ('volume up', 'battery', 'lock my pc', 'put my pc to sleep', "
            "'brightness 80', 'next track', 'show desktop'), 'how is the pc', 'take a photo'. "
            "Commands: /plan /draft /summarize /code /think /welcome — full list in /help.")


def _speak(ctx, m):
    from ..voice import speak
    ok = speak.speak(m.group(1).strip(), ctx.cfg)
    return "Spoken." if ok else "TTS unavailable right now — check /tts."


FASTPATHS: list[FastPath] = [
    FastPath("time", re.compile(r"^(what\s+time\s+is\s+it|what\s+is\s+the\s+time|what's\s+the\s+time|time\s+now)\b[?.!]*$", re.I), _time),
    FastPath("date", re.compile(r"^(what('s|\s+is)?\s+the\s+date|today('s|\s+is)?\s+(the\s+)?date|what\s+day\s+is\s+it)\b[?.!]*$", re.I), _date),
    FastPath("uptime", re.compile(r"^(how\s+long\s+has\s+(the\s+)?(pc|computer|machine)\s+been\s+on|system\s+uptime|uptime)\b[?.!]*$", re.I), _uptime),
    FastPath("weather", re.compile(r"^(?:what('s|\s+is)?\s+(?:the\s+)?weather|weather)(?:\s+(?:in|for|at)\s+([A-Za-z][A-Za-z ]{0,30}))?\s*[?.!]*$", re.I), _weather),
    FastPath("convert", re.compile(r"^(\d+(?:[.,]\d+)?)\s*([a-z°]+)\s*(?:to|in|=|→)\s*([a-z°]+)$", re.I), _convert),
    FastPath("coin", re.compile(r"^flip\s+a\s+coin\b[?.!]*$", re.I), _coin),
    FastPath("dice", re.compile(r"^roll\s+(?:a\s+)?die\b[?.!]*$", re.I), _dice),
    FastPath("random", re.compile(r"^random\s+(?:number|int(?:eger)?|value)\s+(?:between|from)\s+(\d+)\s*(?:and|to|-)\s*(\d+)$", re.I), _random_between),
    FastPath("pick", re.compile(r"^(?:pick|choose|select)\s+(?:one|any)\s+of\s+([A-Za-z0-9 ,.&'-]{3,200})$", re.I), _pick),
    FastPath("open_profile", re.compile(r"^(?:please\s+)?(?:open|launch|start)\s+(chrome|edge)(?:\.com)?\b.*?(?:user|profile|account)\s*(\d+)\b[?.!]*$", re.I), _open_profile),
    FastPath("open_app", re.compile(r"^(?:please\s+)?(?:open|launch|start)\s+(google chrome|chrome|microsoft edge|edge|notepad|word|excel|powerpoint|outlook|mail|file explorer|explorer|this pc|cmd|terminal|powershell|paint|calculator|vscode|code|spotify|discord|slack|zoom|task manager|settings|camera|photos|microsoft store|store|maps|whatsapp|telegram|gmail|youtube|grok|accio|yt)\b[?.!]*$", re.I), _open_app),
    FastPath("open_inverted", re.compile(r"^(chrome|edge|whatsapp|camera|telegram|spotify|discord|zoom|outlook|excel|word|notepad|terminal|powershell|paint|calculator|vscode|settings|photos|maps|gmail|youtube|grok|slack|yt)\s+(launch|open|start)(?:\s+now)?\b[?.!]*$", re.I), _open_inverted),
    FastPath("open_file", re.compile(r"^(?:open|show|reveal)\s+([\w][\w./\\ -]*\.(?:md|txt|json|ya?ml|py|csv|html?|log))$", re.I), _open_file),
    FastPath("open_domain", re.compile(r"^(?:please\s+)?(?:open|launch|visit|go to)\s+((?:https?://)?[a-z0-9-]+(?:\.[a-z0-9-]+)+[a-z0-9/._%?&=#-]*)\s*[?.!]*$", re.I), _open_domain),
    FastPath("search", re.compile(r"^(?:please\s+)?(?:search(?:\s+google)?|google|look\s+up|find\s+online)\s+(?!your\s+memory\b|my\s+memory\b|the\s+memory\b|memory\s+for\b)(?:for\s+)?([A-Za-z0-9][A-Za-z0-9 ,.'&-]{2,160})$", re.I), _search),
    FastPath("creator", re.compile(r"^(?:who|who's|whos)\s+(?:created|made|built|wrote|developed|designed)\s+(?:you|bee|this)\b[?.!]*$", re.I), _creator),
    # spoken reminders ("remind me to stretch in 20 min") — same durable job,
    # same parser and same delivery as /remind, with no model call and no
    # provider needed at fire time. Listed BEFORE wikipedia/identity because
    # "what are my reminders" otherwise reads as a definitional question.
    FastPath("remind_list", re.compile(
        r"^(?:(?:what|which)\s+(?:are|is)\s+my\s+reminders?|"
        r"(?:show|list|check)(?:\s+me)?\s+(?:my\s+|all\s+)?reminders?|"
        r"do\s+i\s+have(?:\s+any)?\s+reminders?)\s*[?.!]*$", re.I), _remind_list),
    FastPath("remind_cancel_last", re.compile(
        r"^(?:please\s+)?(?:cancel|delete|remove|stop)\s+(?:my|the)\s+"
        r"(?:last|latest|most\s+recent)\s+reminders?\s*(?:please)?[?.!]*$", re.I),
        lambda ctx, m: _remind_cancel(ctx, "last")),
    FastPath("remind_cancel_all", re.compile(
        r"^(?:please\s+)?(?:cancel|delete|remove|clear)\s+all\s+(?:of\s+)?(?:my\s+)?"
        r"reminders?\s*(?:please)?[?.!]*$", re.I),
        lambda ctx, m: _remind_cancel(ctx, "all")),
    FastPath("files_list", _FILES_HEAD, _files_list),
    FastPath("run_code", re.compile(
        r"^(?:please\s+)?(?:run|execute|try)\s+(?:the\s+|this\s+)?(?:following\s+)?"
        r"(?:python|py|python3)(?:\s+(?:code|snippet|script|program))?\s*[:\-–]\s*"
        r"(?P<c>.+)$", re.I), _run_code, max_len=4000),
    FastPath("remind", re.compile(
        r"^(?:please\s+)?(?:remind\s+me\s+(?:to|about|that)|remind\s+me|"
        r"don['’]t\s+forget\s+to|don['’]t\s+forget|"
        r"set\s+(?:up\s+)?(?:a|an)\s+reminder\s+(?:to|for|about)|"
        r"add\s+(?:a\s+)?reminder\s+(?:to|for|about)|reminder\s*[:|-])"
        r"\s*[:\-]?\s+(.+)$", re.I), _remind),
    FastPath("specs", re.compile(
        r"^(?:"
        r"(?:what\s+(?:are|is)|what['’]s|which\s+(?:are|is))\s+(?:my|this|the)\s+"
        r"(?:(?:machine|pc|computer|laptop|system|device|hardware)(?:'s)?\s+)?"
        r"(?:specs?\b|specifications?\b|hardware\b|cpu\b|processor\b|gpu\b|"
        r"graphics\s+card\b|ram\b|memory\b)"
        r"|(?:what|which)\s+(?:gpu|cpu|graphics\s+card|processor|ram|memory)\s+"
        r"(?:do\s+i\s+have|is\s+(?:in|on|inside)\s+(?:my|this|the)\s+"
        r"(?:machine|pc|computer|laptop|system))"
        r")(?:\s+(?:do\s+i\s+have|this\s+machine\s+has))?[\s?.!]*$", re.I), _specs),
    FastPath("identity", re.compile(r"^(who\s+are\s+you|what\s+are\s+you|your\s+name|are\s+you\s+bee)\b[?.!]*$", re.I), _identity),
    FastPath("wikipedia", re.compile(r"^(?:what is|who is|what are|who are|tell me about|wiki(?:pedia)?(?:\s+on)?)\s+(?!you\b|bee\b)(.+)$", re.I), _wikipedia),
    FastPath("play", re.compile(r"^(?:please\s+)?(?:play|put\s+on)\s+(?!pause\b|stop\b|next\b|previous\b)([A-Za-z0-9][A-Za-z0-9' ,.&-]{2,120})$", re.I), _play),
    FastPath("youtube", re.compile(r"^youtube\s+([A-Za-z0-9][A-Za-z0-9' ,.&-]{2,120})$", re.I), _play),
    # 'remember X' is deliberately NOT a fast path — it's ambiguous between a
    # plain note and a memory reference, which needs the model + memory tools.
    FastPath("note", re.compile(r"^(?:note|jot\s+down)\s+(?:that\s+)?(.+)$", re.I), _note),
    FastPath("todo", re.compile(r"^(?:add\s+)?(?:todo|to-do|task)\s*:?\s+(.+)$", re.I), _todo),
    FastPath("media_pause", re.compile(r"^(?:pause|stop)\s+(?:the\s+)?(?:music|song|track|playback|video|audio)\b", re.I), _media_factory("pause")),
    FastPath("media_resume", re.compile(r"^(?:resume|continue|unpause)\s+(?:the\s+)?(?:music|song|playback|video|audio)\b", re.I), _media_factory("resume")),
    FastPath("media_next", re.compile(r"^(?:next\s+(?:track|song|video)|skip\s+(?:to\s+)?(?:the\s+)?next\s+(?:track|song|video))\b", re.I), _media_factory("next")),
    FastPath("media_prev", re.compile(r"^(?:previous\s+(?:track|song|video)|go\s+back\s+(?:a\s+)?(?:track|song|video))\b", re.I), _media_factory("prev")),
    FastPath("volume", re.compile(r"^(?:turn\s+(?:the\s+)?(?:volume|sound|music)\s+|(?:set\s+)?volume\s+)(up|down|max|maximum|mute|unmute|louder|quieter|increase|decrease|higher|lower)\b", re.I), _volume),
    FastPath("battery", re.compile(r"^(?:how\s+much\s+(?:is\s+the\s+)?battery|battery\s+(?:level|status|percent|charge|remaining)|check\s+the?\s+battery)\b[?.!]*$", re.I), _battery),
    FastPath("lock", re.compile(r"^(?:please\s+)?lock(?:\s+(?:down|the|screen|my\s+(?:pc|computer|screen|workstation|laptop)))?\b[?.!]*$", re.I), _lock),
    FastPath("sleep", re.compile(r"^(?:please\s+)?(?:put|send|set)\s+(?:my\s+)?(?:pc|computer|laptop|system)\s+to\s+sleep$|^sleep\s+(?:my\s+)?(?:pc|computer|laptop|system)$", re.I), _sleep),
    FastPath("brightness", re.compile(r"^(?:set\s+)?(?:the\s+)?brightness\s+(?:to\s+)?(\d{1,3})(?:%)?$", re.I), _brightness),
    FastPath("show_desktop", re.compile(r"^(?:show\s+(?:the\s+)?desktop|minimize\s+all\s+(?:windows|apps|tasks)|clean\s+up\s+the\s+desktop)$", re.I), _show_desktop),
    FastPath("welcome", re.compile(r"^(?:welcome\s+home|run\s+the?\s+welcome\s+(?:protocol|sequence)|start\s+the?\s+welcome\s+(?:protocol|sequence))\b", re.I), _welcome),
    FastPath("photo", re.compile(r"^(?:take|snap)\s+(?:a\s+)?(?:photo|pic|picture|selfie)$", re.I), _photo),
    FastPath("sysstats", re.compile(r"^(?:how much (?:ram|memory) (?:is )?(?:free|used|left)|free ram|system (?:stats|status|info|health)|disk (?:space|usage)|ram usage|how('s| is) (the )?(?:pc|computer|system)(?: doing)?)\b[?.!]*$", re.I), _sysstats),
    FastPath("ip", re.compile(r"^(?:what('s|\s+is)? my (?:public )?ip|show my ip|my ip address)\b[?.!]*$", re.I), _public_ip),
    FastPath("plate", re.compile(r"^(what('s|\s+is)?\s+(?:on\s+my\s+plate|my\s+schedule|on\s+my\s+agenda|today))\b[?.!]*$", re.I), _plate),
    FastPath("speak", re.compile(r"^speak\s+(.+)$", re.I), _speak),
    FastPath("help", re.compile(r"^help\b[?.!]*$", re.I), _help),
]


def match(task: str) -> Optional[tuple[FastPath, "re.Match"]]:
    t = (task or "").strip()
    if not t:
        return None
    for fp in FASTPATHS:
        if len(t) > fp.max_len:
            continue
        m = fp.rx.search(t)
        if m:
            return fp, m
    return None
