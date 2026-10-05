"""automate tool: workspace confinement + recipe correctness (no real fs side effects)."""
import json
from pathlib import Path

from bee.tools.automate import _run


class _Ctx:
    def __init__(self, ws):
        self.workspace = str(ws)


def _ctx(tmp_path):
    return _Ctx(tmp_path)


def test_inventory(tmp_path):
    (tmp_path / "a.txt").write_text("hi")
    (tmp_path / "b.py").write_text("x=1")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "c.txt").write_text("hello world")
    r = _run(_ctx(tmp_path), "inventory", path=".")
    assert r["file_count"] == 3
    assert r["by_extension"].get(".txt") == 2
    assert r["by_extension"].get(".py") == 1


def test_path_escape_rejected(tmp_path):
    r = _run(_ctx(tmp_path), "inventory", path="..")
    assert "error" in r and "workspace" in r["error"]


def test_rename_dry_run_then_real(tmp_path):
    (tmp_path / "photo_1.jpg").write_text("x")
    (tmp_path / "photo_2.jpg").write_text("x")
    dry = _run(_ctx(tmp_path), "rename", path=".", pattern="photo_", replacement="img_", dry_run=True)
    assert dry["dry_run"] is True and dry["changed"] == 2
    assert (tmp_path / "photo_1.jpg").exists()  # not renamed yet
    real = _run(_ctx(tmp_path), "rename", path=".", pattern="photo_", replacement="img_", dry_run=False)
    assert real["changed"] == 2
    assert (tmp_path / "img_1.jpg").exists() and not (tmp_path / "photo_1.jpg").exists()


def test_convert_csv_to_jsonl(tmp_path):
    (tmp_path / "d.csv").write_text("name,age\nalice,3\nbob,4\n", encoding="utf-8")
    r = _run(_ctx(tmp_path), "convert", path="d.csv", from_format="csv", to_format="jsonl")
    assert r["rows"] == 2
    out = Path(r["out"]); assert out.exists()
    rows = [json.loads(l) for l in out.read_text(encoding="utf-8").splitlines()]
    assert rows[0] == {"name": "alice", "age": "3"}


def test_dedupe(tmp_path):
    (tmp_path / "l.txt").write_text("a\nb\na\nc\nb\n", encoding="utf-8")
    r = _run(_ctx(tmp_path), "dedupe", path="l.txt")
    assert r["lines_in"] == 5 and r["lines_out"] == 3 and r["removed"] == 2


def test_lines_grep_sort_unique(tmp_path):
    (tmp_path / "l.txt").write_text("banana\napple\ncherry\napple\n", encoding="utf-8")
    g = _run(_ctx(tmp_path), "lines", path="l.txt", contains="app")
    assert g["lines"] == ["apple", "apple"]
    s = _run(_ctx(tmp_path), "lines", path="l.txt", sort=True, unique=True)
    assert s["lines"] == ["apple", "banana", "cherry"]


def test_fill_dry_run(tmp_path):
    (tmp_path / "t.txt").write_text("Hello {{name}}, you are $age.", encoding="utf-8")
    r = _run(_ctx(tmp_path), "fill", path="t.txt",
             mapping={"name": "Mshri", "age": 5}, dry_run=True)
    assert r["dry_run"] is True and "Mshri" in r["preview"] and "5" in r["preview"]
    assert (tmp_path / "t.txt").read_text(encoding="utf-8").startswith("Hello {{name}}")  # unchanged


def test_jsonq(tmp_path):
    (tmp_path / "d.json").write_text(
        json.dumps({"a": {"b": [{"c": 1}, {"c": 2}]}, "n": [10, 20, 30]}), encoding="utf-8")
    r = _run(_ctx(tmp_path), "jsonq", path="d.json", jq="a.b[*].c")
    assert r["values"] == [1, 2]
    assert _run(_ctx(tmp_path), "jsonq", path="d.json", jq="n[1]")["values"] == [20]
    (tmp_path / "e.jsonl").write_text('{"id": 1, "t": "x"}\n{"id": 2, "t": "y"}\n',
                                      encoding="utf-8")
    assert _run(_ctx(tmp_path), "jsonq", path="e.jsonl", jq="id")["values"] == [1, 2]


def test_count(tmp_path):
    (tmp_path / "c.txt").write_text("one two three\nfoo\nfoo bar\n", encoding="utf-8")
    r = _run(_ctx(tmp_path), "count", path="c.txt")
    assert r["lines"] == 3 and r["words"] == 6 and r["chars"] > 0
    rp = _run(_ctx(tmp_path), "count", path="c.txt", mode="pattern", pattern="foo")
    assert rp["lines_matching"] == 2 and rp["occurrences"] == 2


def test_find(tmp_path):
    (tmp_path / "x.py").write_text("import os\n", encoding="utf-8")
    (tmp_path / "y.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "z.txt").write_text("notes\n", encoding="utf-8")
    assert _run(_ctx(tmp_path), "find", path=".", glob="*.py")["count"] == 2
    r = _run(_ctx(tmp_path), "find", path=".", glob="*.py", contains="print")
    assert r["count"] == 1 and r["files"][0]["rel"].endswith("y.py")


def test_zip_create_extract(tmp_path):
    d = tmp_path / "stuff"; d.mkdir()
    (d / "a.txt").write_text("alpha\n", encoding="utf-8")
    (d / "b.txt").write_text("beta\n", encoding="utf-8")
    rc = _run(_ctx(tmp_path), "zip", path="stuff", mode="create", archive="out.zip")
    assert "created" in rc and Path(rc["created"]).exists()
    _run(_ctx(tmp_path), "zip", path="out.zip", mode="extract", archive="extracted")
    assert (tmp_path / "extracted" / "stuff" / "a.txt").read_text(encoding="utf-8") == "alpha\n"
    assert (tmp_path / "extracted" / "stuff" / "b.txt").exists()
