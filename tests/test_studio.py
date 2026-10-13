import base64
import hashlib
import io
import zipfile

import pytest
from flask import Flask

from api.domain.studio import providers as providers_mod
from api.domain.studio import routes as routes_mod
from api.domain.studio.builders import PdfReportBuilder, latin1, text_blocks
from api.domain.studio.pipeline import Change, build_context, validate_plan
from api.domain.studio.providers import ProviderError, TaskProvider, parse_json_object
from api.domain.studio.routes import studio_bp
from api.domain.studio.sources import FilesSource, Project, SourceError, ZipSource, safe_path, source_for

REPORT = {"objective": "Add a greeting helper.", "approach": "- Added `greet` to app.py.\n- Wrote a test.",
          "implementation_details": "greet() returns a string.\n```python\ndef greet(n):\n    return f'hi {n}'\n```",
          "how_to_run": "python -m pytest", "results_and_testing": "tests/test_app.py checks greet().",
          "limitations_next_steps": "None."}


def answer(changes, **extra):
    return {"title": "Greeting helper", "summary": "Added a greet function. Added a test for it.",
            "steps": ["Read app.py.", "Added greet()."], "changes": changes,
            "readme_md": "# Demo\n\nRun `python app.py`.", "report": REPORT, "notes": ["Assumed Python 3.10."], **extra}


class FakeProvider(TaskProvider):
    name = "fake"
    calls = []

    def __init__(self, result):
        self.result = result

    def run(self, prompt, project_context, title=None):
        FakeProvider.calls.append({"prompt": prompt, "context": project_context, "title": title})
        out = self.result() if callable(self.result) else self.result
        if isinstance(out, dict):
            out = {**out, "model": "fake-pro"}
        return out


@pytest.fixture
def use_provider(monkeypatch):
    FakeProvider.calls = []

    def install(result):
        monkeypatch.setitem(providers_mod.PROVIDERS, "gemini", lambda: FakeProvider(result))
    return install


@pytest.fixture(scope="module")
def client():
    app = Flask(__name__)
    app.register_blueprint(studio_bp)
    return app.test_client()


def make_zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def post(client, files, prompt="add a greet function and a test", **fields):
    data = {"prompt": prompt, **fields}
    data["files"] = [(io.BytesIO(content), name) for name, content in files]
    return client.post("/api/studio/run", data=data, content_type="multipart/form-data")


def unzip(data):
    zf = zipfile.ZipFile(io.BytesIO(base64.b64decode(data["zip_b64"])))
    return {n: zf.read(n) for n in zf.namelist()}


# ---------------- round trips ----------------
def test_zip_upload_round_trip(client, use_provider):
    use_provider(answer([
        {"path": "proj/app.py", "action": "update", "why": "Added greet().", "content": "def greet(n):\n    return f'hi {n}'\n"},
        {"path": "proj/tests/test_app.py", "action": "create", "why": "Covers greet().", "content": "from app import greet\n"},
    ]))
    upload = make_zip({"proj/app.py": "print('hi')\n", "proj/logo.png": b"\x89PNG\x00\x01binary",
                       "proj/node_modules/x/index.js": "junk", "__MACOSX/proj/._app.py": "mac", "proj/.DS_Store": "x"})
    res = post(client, [("project.zip", upload)], title="Lab 3", author="Sai")
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    assert data["model"] == "fake-pro" and data["title"] == "Lab 3"
    assert data["summary"].startswith("Added a greet function")
    assert data["changes"] == [{"path": "proj/app.py", "action": "update", "why": "Added greet()."},
                               {"path": "proj/tests/test_app.py", "action": "create", "why": "Covers greet()."}]
    assert data["zip_name"].endswith(".zip") and data["pdf_name"].endswith(".pdf")
    files = unzip(data)
    assert sorted(files) == ["proj/README.md", "proj/REPORT.pdf", "proj/app.py", "proj/logo.png", "proj/tests/test_app.py"]
    assert files["proj/app.py"].startswith(b"def greet")
    assert files["proj/logo.png"] == b"\x89PNG\x00\x01binary"  # binaries kept unchanged
    assert files["proj/README.md"].decode() == data["readme_md"] == "# Demo\n\nRun `python app.py`."
    assert files["proj/REPORT.pdf"].startswith(b"%PDF")
    assert base64.b64decode(data["pdf_b64"]).startswith(b"%PDF")
    assert any("node_modules/" in n for n in data["notes"])
    # the model saw the source file but not the binary or node_modules contents
    ctx = FakeProvider.calls[0]["context"]
    assert "=== FILE: proj/app.py ===" in ctx and "proj/logo.png" in ctx and "binary, not shown" in ctx
    assert "node_modules" not in ctx and "=== FILE: proj/logo.png" not in ctx
    assert FakeProvider.calls[0]["title"] == "Lab 3"


def test_folder_upload_keeps_relative_paths_and_existing_readme(client, use_provider):
    use_provider(answer([{"path": "site/src/main.py", "action": "update", "why": "Fix.", "content": "x = 2\r\n"}]))
    res = post(client, [("site\\src\\main.py", b"x = 1\r\n"), ("site/README.md", b"# Old"), ("site/data/notes.txt", b"n")])
    assert res.status_code == 200, res.get_json()
    data = res.get_json()["data"]
    files = unzip(data)
    assert sorted(files) == ["site/README.md", "site/README_STUDIO.md", "site/REPORT.pdf", "site/data/notes.txt", "site/src/main.py"]
    assert files["site/README.md"] == b"# Old"  # never clobbered
    assert files["site/src/main.py"] == b"x = 2\r\n"
    assert any("README_STUDIO.md" in n for n in data["notes"])


def test_single_file_upload_and_delete(client, use_provider):
    use_provider(answer([{"path": "old.py", "action": "delete", "why": "Unused."},
                         {"path": "main.py", "action": "update", "why": "Inline old.py.", "content": "print(1)\n"}],
                        readme_md=""))
    res = post(client, [("main.py", b"import old\n"), ("old.py", b"x = 1\n")])
    data = res.get_json()["data"]
    files = unzip(data)
    assert "old.py" not in files and files["main.py"] == b"print(1)\n"
    assert {"path": "old.py", "action": "delete", "why": "Unused."} in data["changes"]
    assert "README.md" in files and files["README.md"].decode().startswith("# Greeting helper")  # fallback README


def test_info_endpoint(client, monkeypatch):
    monkeypatch.setenv("STUDIO_MODELS", "gemini-x-pro, gemini-y-flash")
    data = client.get("/api/studio/info").get_json()["data"]
    assert data["max_upload_mb"] == 4 and data["models"] == ["gemini-x-pro", "gemini-y-flash"]


# ---------------- path safety ----------------
@pytest.mark.parametrize("bad", ["../evil.py", "a/../../evil.py", "/etc/passwd", "C:\\Windows\\x.dll", "C:/x.py", "..\\x.py", "", "a/\x00b"])
def test_safe_path_rejects(bad):
    assert safe_path(bad) is None


def test_safe_path_normalises():
    assert safe_path("proj\\src\\main.py") == "proj/src/main.py"
    assert safe_path("./a//b/./c.txt") == "a/b/c.txt"


def test_zip_slip_entries_are_rejected(client, use_provider):
    use_provider(answer([]))
    upload = make_zip({"../../evil.py": "boom", "/abs.py": "boom", "ok/main.py": "print(1)\n"})
    project = ZipSource(upload).load()
    assert list(project.files) == ["ok/main.py"] and len(project.rejected) == 2
    res = post(client, [("p.zip", upload)])
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert all("evil" not in n and "abs" not in n for n in unzip(data))
    assert any("outside the project" in n for n in data["notes"])


def test_folder_upload_rejects_unsafe_names():
    project = FilesSource([("../x.py", b"1"), ("/root.py", b"1"), ("good/a.py", b"1")]).load()
    assert list(project.files) == ["good/a.py"] and len(project.rejected) == 2
    with pytest.raises(SourceError):
        FilesSource([("../x.py", b"1")]).load()


def test_bad_zip_is_400(client, use_provider):
    use_provider(answer([]))
    res = post(client, [("p.zip", b"not a zip")])
    assert res.status_code == 400 and "zip" in res.get_json()["message"].lower()


def test_source_factory():
    assert isinstance(source_for([("a.zip", b"")]), ZipSource)
    assert isinstance(source_for([("a.zip", b""), ("b.py", b"")]), FilesSource)


# ---------------- request errors ----------------
def test_missing_prompt_or_files_is_400(client, use_provider):
    use_provider(answer([]))
    assert post(client, [("a.py", b"1")], prompt="  ").status_code == 400
    res = client.post("/api/studio/run", data={"prompt": "do it"}, content_type="multipart/form-data")
    assert res.status_code == 400 and res.get_json()["status"] == "error"
    assert post(client, [("a.py", b"1")], prompt="x" * 4001).status_code == 400
    assert FakeProvider.calls == []


def test_oversize_is_413(client, use_provider):
    use_provider(answer([]))
    big = b"a" * (2 * 1024 * 1024 + 10)
    res = post(client, [("a.txt", big), ("b.txt", big)])
    assert res.status_code == 413 and res.get_json()["status"] == "error"
    assert FakeProvider.calls == []


def test_provider_garbage_is_502(client, use_provider):
    use_provider("not even json")
    res = post(client, [("a.py", b"1")])
    assert res.status_code == 502 and "format" in res.get_json()["message"]
    use_provider({"foo": 1})
    res = post(client, [("a.py", b"1")])
    assert res.status_code == 502 and "expected fields" in res.get_json()["message"]

    def boom():
        raise RuntimeError("All LLM providers failed.")
    use_provider(boom)
    res = post(client, [("a.py", b"1")])
    assert res.status_code == 502 and "All LLM providers failed" in res.get_json()["message"]


def test_parse_json_object():
    assert parse_json_object('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json_object('Here you go: {"a": 2} thanks') == {"a": 2}
    for bad in ("nope", "[1, 2]", '{"a": '):
        with pytest.raises(ProviderError):
            parse_json_object(bad)


# ---------------- validation ----------------
def test_invalid_change_entries_dropped_with_notes():
    project = Project(files={"a.py": b"x = 1\n", "img.png": b"\x89PNG\x00", "big.csv": b"h\n" + b"1\n" * 10})
    ctx = build_context(project)
    ctx.previews.add("big.csv")
    plan = validate_plan(answer([
        {"path": "../evil.py", "action": "create", "why": "", "content": "x"},
        {"path": "/abs.py", "action": "create", "content": "x"},
        {"path": "b.py", "action": "explode", "content": "x"},
        {"path": "c.py", "action": "create"},
        {"path": "nope.py", "action": "delete"},
        {"path": "img.png", "action": "update", "content": "text"},
        {"path": "big.csv", "action": "update", "content": "h\n"},
        {"path": "a.py", "action": "update", "content": "x = 1\n"},
        {"path": "a.py/inner.py", "action": "create", "content": "y"},
        "not a dict",
        {"path": "node_modules/x.js", "action": "create", "content": "x"},
        {"path": "new.py", "action": "update", "why": "New helper.", "content": "def f():\n    pass\n"},
    ]), project, ctx)
    assert [(c.path, c.action) for c in plan.changes] == [("new.py", "create")]  # update of a new file -> create
    joined = " | ".join(plan.notes)
    for fragment in ("../evil.py", "/abs.py", "unknown action", "no file content", "does not exist", "binary",
                     "preview", "identical", "clashes", "not an object", "ignored folder"):
        assert fragment in joined, fragment
    assert plan.notes[-1] == "Assumed Python 3.10."  # model notes kept after ours


def test_context_cap_prefers_small_source_files():
    project = Project(files={"src/main.py": b"print(1)\n", "data/huge.csv": b"a,b\n" + b"1,2\n" * 5000,
                             "package-lock.json": b"{}" * 10})
    ctx = build_context(project, max_chars=3000)
    assert "src/main.py" in ctx.included
    assert "data/huge.csv" in ctx.previews and "PREVIEW ONLY" in ctx.text
    assert "data/huge.csv" in ctx.text.split("FILE CONTENTS:")[0]  # still listed
    tiny = build_context(project, max_chars=600)
    assert tiny.omitted.get("data/huge.csv") == "not shown: over the context limit"


# ---------------- pdf ----------------
def test_pdf_sanitization_does_not_crash():
    text = "\u201cSmart quotes\u201d \u2014 dash \u2026 bullet \u2022 emoji \U0001F680 \u4e2d\u6587 caf\u00e9 \u0141\u00f3d\u017a"
    clean = latin1(text)
    assert clean == '"Smart quotes" - dash ... bullet - emoji   caf\u00e9 L\u00f3dz'
    clean.encode("latin-1")  # nothing outside latin-1 survives
    long_path = "src/" + "deeply_nested_folder/" * 20 + "file.py"
    pdf = (PdfReportBuilder(text, author="S\u00e3i \U0001F600", purpose=text, summary=text)
           .section("Objective", text + "\n- bullet \u2192 arrow\n## Sub\n```\ncode \u2713\n```\n" + "x" * 500)
           .changes_table("Changes", [Change(long_path, "update", text * 3, b"")])
           .build())
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000


def test_text_blocks():
    blocks = list(text_blocks("Para one\ncontinues.\n\n- a\n* b\n1. c\n## Head\n```\ncode\n```\nend"))
    assert blocks == [("para", "Para one continues."), ("bullet", "a"), ("bullet", "b"), ("bullet", "1. c"),
                      ("subhead", "Head"), ("code", ["code"]), ("para", "end")]


# ---------------- auth ----------------
def test_studio_requires_passcode(monkeypatch, use_provider):
    from api.app import app
    use_provider(answer([]))
    monkeypatch.setenv("APP_PASSCODE", "secret-code")
    c = app.test_client()
    assert c.get("/api/studio/info").status_code == 401
    assert c.post("/api/studio/run", data={"prompt": "x"}, content_type="multipart/form-data").status_code == 401
    token = hashlib.sha256(b"daily:secret-code").hexdigest()
    assert c.get("/api/studio/info", headers={"X-App-Key": token}).status_code == 200
    res = c.post("/api/studio/run", headers={"X-App-Key": token}, content_type="multipart/form-data",
                 data={"prompt": "x", "files": [(io.BytesIO(b"print(1)\n"), "a.py")]})
    assert res.status_code == 200 and res.get_json()["data"]["pdf_b64"]
