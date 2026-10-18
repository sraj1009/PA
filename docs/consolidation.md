# Memory design — consolidation & self-improvement

## Memory layers
| Layer | Where | Written by | Read by |
|---|---|---|---|
| Episodic | `memory/diary/YYYY-MM-DD.md` | auto after every task + `diary_add` | nightly consolidation |
| Lessons | `memory/lessons/YYYY-MM-DD.md` | `reflection.py` after every task | system prompt (last 3 days) |
| Durable facts | `memory/longterm.md` | `memory_longterm`, consolidation | system prompt (always) |
| User profile | `memory/profile.md` | `profile_add` | system prompt (always) |
| Semantic | `memory/vectors/` (LanceDB) | 12h rebuild job + on demand | `memory_search` (vector mode) |
| Capabilities | `skills/<name>/SKILL.md` | `skill_create` (agent) | system prompt index + `skill_get` |

## Consolidation (nightly 03:00, `bee/scheduler.py`)
1. Collect diary files older than 7 days.
2. Local LLM summarizes them into ≤ 8 durable bullets.
3. Bullets appended to `longterm.md` (dedupe by eyeball: agent edits).
4. Old diary files archived to `memory/diary/archive/` (never deleted — a bad
   summary must not destroy the originals; see `bee/scheduler.py:56-72`).
5. LanceDB index rebuilt from all current markdown.

## The self-improvement loops
1. **Reflection (every task):** `reflection.reflect()` writes worked/failed/next bullets → lessons. Cheap (local model, ~100 tokens out).
2. **Skills (novel successes):** system prompt instructs BEE to `skill_create` anything reusable. Skills load on demand (`skill_get`) — context cost is one line each until used.
3. **Prompt self-edit (human-approved):** BEE proposes edits to `memory/system.md` / `profile.md` in chat; you approve; it applies via `file_edit`. Never autonomous.
4. **Evals (the gate):** `python -m bee.cli eval` — every change (model swap, prompt edit, new skills, fine-tune) is adopted only if evals/tasks.yaml score improves. History in `evals/results.jsonl`.
5. **Fine-tune (Phase 4, optional):** QLoRA Qwen3-8B on successful traces (`skills/finetune/`), gated by evals.

## Safety rails
- File tools are jailed to the workspace (path traversal rejected).
- `calculator` is AST-whitelisted (no imports, no statements).
- Destructive/heavy work → `sandbox_run` (Docker).
- Voice is fully local (faster-whisper int8 on the 3050 for base.en).
