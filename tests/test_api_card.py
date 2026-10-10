"""A50: a request that names one of BEE's own modules gets that module's REAL
signatures, read from source with `ast` (never imported).

Live evidence (evals/results.jsonl, ~30 runs of `dsa_graph`): the local model knew
the module name `bee.dsa.graphs` (A45c put it in the skills index) but never its
API — it wrote `Graph()`, `graph.add_edge(...)`, `from bee_dsa import graphs`, and
the snippet that ran died with AttributeError / ModuleNotFoundError.
"""
from __future__ import annotations

from bee.agent.context import module_api_card
from tests.test_kernel_integration import _no_fastpath, make_kernel

DSA_TASK = ("Run python to import bee.dsa.graphs, build edges A-B(1), B-C(2), A-C(10), "
            "and print dijkstra distance from A to C.")


def test_card_lists_the_real_public_signatures():
    card = module_api_card(DSA_TASK)
    assert "bee.dsa.graphs" in card
    assert "dijkstra(adj: dict, start)" in card
    assert "build_adj(nodes=None, edges=None) -> dict" in card
    assert "(u, v, w)" in card            # the edge format the model has to get right
    assert "_adj(" not in card.replace("build_adj(", "")   # private helpers stay out


def test_an_attribute_path_resolves_to_its_module():
    card = module_api_card("what does bee.dsa.graphs.dijkstra return?")
    assert "dijkstra(adj: dict, start)" in card


def test_names_that_are_not_project_modules_add_nothing():
    for text in ("open example.com and read notes.txt",
                 "use os.path.join and numpy.linalg",
                 "version 3.11 of bee",
                 "import bee.no_such_module"):
        assert module_api_card(text) == "", text


def test_the_card_is_bounded():
    card = module_api_card("compare bee.dsa.graphs, bee.dsa.trie, bee.dsa.heap, "
                           "bee.dsa.sorting and bee.dsa.dp")
    assert 0 < len(card) <= 3200
    assert card.count("Real API of") <= 2


def test_the_model_sees_the_card_in_the_request(tmp_path, monkeypatch):
    _no_fastpath(monkeypatch)
    k, client, _ctx = make_kernel(tmp_path, ["The distance is 3."])
    k.run(DSA_TASK)
    first_user = next(m["content"] for m in client.calls[0][1] if m["role"] == "user")
    assert first_user.startswith(DSA_TASK)
    assert "dijkstra(adj: dict, start)" in first_user
