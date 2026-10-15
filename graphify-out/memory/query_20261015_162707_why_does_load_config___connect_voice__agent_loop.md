---
type: "query"
date: "2026-10-15T16:27:07.464261+00:00"
question: "Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?"
contributor: "graphify"
outcome: "useful"
source_nodes: ["load_config()", "AgentKernel", "run_agent()"]
---

# Q: Why does load_config() connect Voice, Agent Loop, LLM Client, ToolBus and 40+ other communities?

## Answer

Expanded from original query via vocab: [load, config, voice, agent, loop, llm, client, toolbus, kernel, memory, context, job]. Traversed BFS from load_config(). load_config() bee/config.py L559 degree 136 touches 48 communities because it is the single config entry point with fan-in imports from tests and services plus fan-out calls to builders.

## Outcome

- Signal: useful

## Source Nodes

- load_config()
- AgentKernel
- run_agent()