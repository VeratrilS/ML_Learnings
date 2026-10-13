"""
Task Studio: the job pipeline.

SYSTEM DESIGN CONCEPT: Template Method
StudioJob.run() fixes the order: load -> build_context -> ask (provider.run) -> validate -> build_outputs.
Each step is a method a subclass can override, and the real work lives in pure functions
(build_context, validate_plan, fallback_readme) so tests can exercise them without the network.
"""
import base64
import posixpath
import re
from dataclasses import dataclass, field
from datetime import datetime

from api.core.config import now_ist
from api.domain.studio.builders import PdfReportBuilder, ZipBuilder, latin1
from api.domain.studio.providers import ProviderError, TaskProvider, get_provider
from api.domain.studio.sources import BINARY_EXTENSIONS, Project, is_excluded, is_junk, is_text, safe_path, source_for

MAX_CONTEXT_CHARS = 600_000
PREVIEW_LINES = 40
PREVIEW_CHARS = 3000
MAX_LISTING = 1500
MAX_CHANGES = 200
MAX_STEPS = 30
MAX_NOTES = 40

SOURCE_EXTENSIONS = {
    ".py", ".ipynb", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".vue", ".svelte", ".java", ".kt", ".kts", ".scala",
    ".c", ".h", ".cpp", ".cc", ".cxx", ".hpp", ".cs", ".go", ".rs", ".rb", ".php", ".swift", ".m", ".r", ".jl", ".lua",
    ".dart", ".sql", ".sh", ".bash", ".ps1", ".bat", ".html", ".htm", ".css", ".scss", ".less", ".md", ".txt", ".rst",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".gradle", ".cmake", ".mk", ".tex", ".env.example",
}
SOURCE_NAMES = {"Makefile", "Dockerfile", "CMakeLists.txt", "requirements.txt", "Procfile", ".gitignore"}
LOW_PRIORITY_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock",
                      "composer.lock", "Cargo.lock", "go.sum", "Gemfile.lock"}

ACTIONS = {"create": "create", "add": "create", "new": "create",
           "update": "update", "modify": "update", "edit": "update", "change": "update", "replace": "update",
           "delete": "delete", "remove": "delete"}
REPORT_KEYS = ("objective", "approach", "implementation_details", "how_to_run", "results_and_testing", "limitations_next_steps")

_EMOJI = re.compile("[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF️‍]")


# ---------------- data ----------------
@dataclass
class ProjectContext:
    text: str
    included: list = field(default_factory=list)   # full files sent
    previews: set = field(default_factory=set)     # only the first lines were sent
    omitted: dict = field(default_factory=dict)    # path -> reason (binary / over the limit)


@dataclass
class Change:
    path: str
    action: str           # create | update | delete
    why: str
    data: bytes = None    # new file bytes (None for delete)


@dataclass
class Plan:
    title: str
    summary: str
    steps: list
    changes: list
    readme_md: str
    report: dict
    notes: list
    model: str


@dataclass
class StudioResult:
    title: str
    summary: str
    steps: list
    changes: list
    notes: list
    model: str
    zip_name: str
    zip_bytes: bytes
    pdf_name: str
    pdf_bytes: bytes
    readme_md: str

    def to_dict(self):
        return {
            "title": self.title, "summary": self.summary, "steps": self.steps,
            "changes": [{"path": c.path, "action": c.action, "why": c.why} for c in self.changes],
            "notes": self.notes, "model": self.model,
            "zip_name": self.zip_name, "zip_b64": base64.b64encode(self.zip_bytes).decode("ascii"),
            "pdf_name": self.pdf_name, "pdf_b64": base64.b64encode(self.pdf_bytes).decode("ascii"),
            "readme_md": self.readme_md,
        }


# ---------------- context ----------------
def _priority(path):
    name = posixpath.basename(path)
    if name in LOW_PRIORITY_NAMES or name.endswith((".min.js", ".min.css", ".map")):
        return 2
    if name in SOURCE_NAMES or posixpath.splitext(name.lower())[1] in SOURCE_EXTENSIONS:
        return 0
    return 1


def _size(n):
    return f"{n} B" if n < 1024 else f"{n / 1024:.1f} KB"


def build_context(project: Project, max_chars: int = MAX_CONTEXT_CHARS) -> ProjectContext:
    """Pick which files the model sees in full, which as a preview, and which only by name.

    Source files and smaller files go first. Everything is listed, so the model knows what exists.
    """
    texts = {}
    ctx = ProjectContext(text="")
    for path, data in project.files.items():
        if is_text(path, data):
            texts[path] = data.decode("utf-8").replace("\r\n", "\n")
        else:
            ctx.omitted[path] = "binary, not shown"

    paths = sorted(project.files)
    listing_reserve = sum(len(p) + 60 for p in paths[:MAX_LISTING]) + 400
    budget = max_chars - listing_reserve
    blocks = {}
    overflow = []
    for path in sorted(texts, key=lambda p: (_priority(p), len(texts[p]), p)):
        block = f"=== FILE: {path} ===\n{texts[path]}\n=== END FILE: {path} ===\n"
        if len(block) <= budget:
            blocks[path] = block
            budget -= len(block)
            ctx.included.append(path)
        else:
            overflow.append(path)
    for path in overflow:
        lines = texts[path].split("\n")
        head = "\n".join(lines[:PREVIEW_LINES])[:PREVIEW_CHARS]
        block = (f"=== FILE: {path} (PREVIEW ONLY: first {min(len(lines), PREVIEW_LINES)} of {len(lines)} lines; "
                 f"do not rewrite this file) ===\n{head}\n=== END PREVIEW: {path} ===\n")
        if len(block) <= budget:
            blocks[path] = block
            budget -= len(block)
            ctx.previews.add(path)
        else:
            ctx.omitted[path] = "not shown: over the context limit"

    listing = []
    for path in paths[:MAX_LISTING]:
        tag = "preview only" if path in ctx.previews else ctx.omitted.get(path)
        listing.append(f"- {path} ({_size(len(project.files[path]))})" + (f" [{tag}]" if tag else ""))
    if len(paths) > MAX_LISTING:
        listing.append(f"- ... and {len(paths) - MAX_LISTING} more files")

    head = [f"PROJECT FILES ({len(paths)} files):", *listing]
    root = root_prefix(paths)
    if root:
        head.append(f"\nAll files are inside the folder '{root}'. Put new files inside it too, unless the task says otherwise.")
    binary = sum(1 for r in ctx.omitted.values() if r.startswith("binary"))
    too_big = len(ctx.omitted) - binary
    if binary or too_big or ctx.previews:
        head.append(f"\nNot shown in full: {binary} binary file(s), {len(ctx.previews)} preview-only file(s), "
                    f"{too_big} file(s) over the context limit (all marked above). Do not rewrite files you have not seen in full.")
    ctx.text = "\n".join(head) + "\n\nFILE CONTENTS:\n" + "".join(blocks[p] for p in sorted(blocks))
    return ctx


# ---------------- validation ----------------
def _clean(value, limit):
    if isinstance(value, list):
        value = "\n".join(f"- {v}" for v in value if isinstance(v, (str, int, float)))
    if not isinstance(value, str):
        return ""
    value = _EMOJI.sub("", value).strip()
    return value[:limit].rstrip() + (" ..." if len(value) > limit else "")


def _one_line(value, limit):
    return _clean(re.sub(r"\s+", " ", value) if isinstance(value, str) else "", limit)


def _str_list(value, limit, max_items):
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [s for s in (_one_line(v, limit) for v in value[:max_items]) if s]


def validate_plan(raw, project: Project, context: ProjectContext = None, user_title: str = None) -> Plan:
    """Schema-check the provider output. Bad change entries are dropped with a note; a useless answer raises."""
    if not isinstance(raw, dict):
        raise ProviderError("The model returned an unexpected format (not a JSON object).")
    raw_changes = raw.get("changes") or []
    if not isinstance(raw_changes, list):
        raise ProviderError("The model returned an unexpected format ('changes' is not a list).")
    report = raw.get("report") if isinstance(raw.get("report"), dict) else {}
    if not any(isinstance(raw.get(k), str) and raw[k].strip() for k in ("summary", "readme_md")) and not raw_changes and not report:
        raise ProviderError("The model's answer had none of the expected fields (summary, changes, readme_md, report).")

    notes = []
    existing = project.files
    previews = context.previews if context else set()
    accepted = {}

    def drop(label, reason):
        notes.append(f"Dropped a change to '{str(label)[:120]}': {reason}.")

    for item in raw_changes[:MAX_CHANGES]:
        if not isinstance(item, dict):
            notes.append("Dropped a change entry that was not an object.")
            continue
        label = item.get("path")
        path = safe_path(label)
        if path is None:
            drop(label, "the path is not a safe relative path")
            continue
        if is_excluded(path) or is_junk(path):
            drop(path, "the path is in an ignored folder")
            continue
        action = ACTIONS.get(str(item.get("action") or "").strip().lower())
        if action is None:
            drop(path, f"unknown action '{str(item.get('action'))[:20]}'")
            continue
        data = None
        if action == "delete":
            if path not in existing:
                drop(path, "the file does not exist")
                continue
        else:
            content = item.get("content")
            if not isinstance(content, str):
                drop(path, "no file content was given")
                continue
            if posixpath.splitext(path.lower())[1] in BINARY_EXTENSIONS or (path in existing and not is_text(path, existing[path])):
                drop(path, "binary files can't be written")
                continue
            if path in previews:
                drop(path, "only a preview of this file was sent to the model, so it was left unchanged")
                continue
            action = "update" if path in existing else "create"
            if path in existing and b"\r\n" in existing[path]:
                content = content.replace("\r\n", "\n").replace("\n", "\r\n")
            data = content.encode("utf-8")
            if path in existing and existing[path] == data:
                notes.append(f"Skipped '{path}': the returned content was identical to the original.")
                continue
        if path in accepted:
            notes.append(f"'{path}' was changed more than once; kept the last version.")
        accepted[path] = Change(path=path, action=action, why=_one_line(item.get("why"), 500) or f"{action.capitalize()}d by the task.", data=data)
    if len(raw_changes) > MAX_CHANGES:
        notes.append(f"Only the first {MAX_CHANGES} changes were applied.")

    # A file and a folder can't share a name (e.g. creating "a.py/x.py" when "a.py" exists).
    final = (set(existing) | {p for p, c in accepted.items() if c.action != "delete"}) - {p for p, c in accepted.items() if c.action == "delete"}
    for path, c in list(accepted.items()):
        if c.action == "create":
            parents = {"/".join(path.split("/")[:i]) for i in range(1, path.count("/") + 1)}
            if parents & final or any(p.startswith(path + "/") for p in final):
                del accepted[path]
                drop(path, "it clashes with an existing file or folder of the same name")

    changes = sorted(accepted.values(), key=lambda c: c.path)
    summary = _one_line(raw.get("summary"), 1200) or (
        f"Made {len(changes)} file change(s) for the task." if changes else "No file changes were made.")
    model_notes = _str_list(raw.get("notes"), 500, MAX_NOTES)
    return Plan(
        title=_one_line(user_title, 150) or _one_line(raw.get("title"), 150) or "Task Studio report",
        summary=summary,
        steps=_str_list(raw.get("steps"), 400, MAX_STEPS),
        changes=changes,
        readme_md=_clean(raw.get("readme_md"), 100_000),
        report={k: _clean(report.get(k), 20_000) for k in REPORT_KEYS},
        notes=(notes + model_notes)[:MAX_NOTES],
        model=_one_line(raw.get("model"), 80) or "unknown",
    )


# ---------------- outputs ----------------
def root_prefix(paths):
    """"proj/" when every file sits in one top-level folder (so README/REPORT go next to the code), else ""."""
    tops = {p.split("/", 1)[0] for p in paths}
    if len(tops) == 1 and all("/" in p for p in paths):
        return tops.pop() + "/"
    return ""


def slugify(text, fallback="task-studio"):
    slug = re.sub(r"[^a-z0-9]+", "-", latin1(text).lower()).strip("-")[:60].strip("-")
    return slug or fallback


def fallback_readme(plan: Plan) -> str:
    lines = [f"# {plan.title}", "", plan.summary, ""]
    if plan.changes:
        lines += ["## What changed", ""] + [f"- `{c.path}` ({c.action}): {c.why}" for c in plan.changes] + [""]
    if plan.steps:
        lines += ["## Steps taken", ""] + [f"{i}. {s}" for i, s in enumerate(plan.steps, 1)] + [""]
    if plan.report.get("how_to_run"):
        lines += ["## How to run", "", plan.report["how_to_run"], ""]
    return "\n".join(lines)


def _free_name(builder: ZipBuilder, preferred, alternative):
    return alternative if builder.has(preferred) else preferred


def build_pdf(plan: Plan, prompt: str, author: str = None, when: datetime = None) -> bytes:
    first_line = next((l.strip() for l in prompt.splitlines() if l.strip()), "")
    purpose = "Task: " + (first_line[:200] + ("..." if len(first_line) > 200 else ""))
    r = plan.report
    steps = "\n".join(f"- {s}" for s in plan.steps)
    return (PdfReportBuilder(plan.title, author=author, date=when, purpose=purpose, summary=plan.summary)
            .section("Objective", r.get("objective") or prompt)
            .section("Approach", r.get("approach") or steps)
            .changes_table("What was changed", plan.changes)
            .section("Key implementation details", r.get("implementation_details"))
            .section("How to run", r.get("how_to_run"), empty="See README.md.")
            .section("Results and testing", r.get("results_and_testing"), empty="No tests were added.")
            .section("Limitations and next steps", r.get("limitations_next_steps"), empty="None noted.")
            .build())


def build_outputs(project: Project, plan: Plan, prompt: str, author: str = None, when: datetime = None) -> StudioResult:
    when = when or datetime.now()
    notes = list(plan.notes)
    zb = ZipBuilder(project.files, when).apply(plan.changes)
    root = root_prefix(zb.files)  # after the changes: new files outside the top folder move README/REPORT up

    readme = plan.readme_md or fallback_readme(plan)
    readme_path = _free_name(zb, root + "README.md", root + "README_STUDIO.md")
    if readme_path.endswith("README_STUDIO.md"):
        notes.append(f"The project already had a README.md, so the new README was saved as {readme_path}.")
    zb.add(readme_path, readme)

    try:
        pdf = build_pdf(plan, prompt, author, when)
    except Exception as e:  # never lose the code changes over a layout problem
        print(f"studio: full report failed, using a plain one: {e}")
        notes.append("The full report could not be laid out, so a shorter report was generated.")
        pdf = (PdfReportBuilder(plan.title, author=author, date=when, summary=plan.summary)
               .section("Summary", plan.summary).build())
    zb.add(_free_name(zb, root + "REPORT.pdf", root + "REPORT_STUDIO.pdf"), pdf)

    slug = slugify(plan.title)
    return StudioResult(title=plan.title, summary=plan.summary, steps=plan.steps, changes=plan.changes,
                        notes=notes[:MAX_NOTES], model=plan.model, zip_name=f"{slug}.zip", zip_bytes=zb.build(),
                        pdf_name=f"{slug}-report.pdf", pdf_bytes=pdf, readme_md=readme)


# ---------------- the job ----------------
class StudioJob:
    def __init__(self, uploads, prompt, title=None, author=None, provider: TaskProvider = None, when=None,
                 max_context_chars=MAX_CONTEXT_CHARS):
        self.uploads = uploads            # [(relative name, bytes)]
        self.prompt = prompt
        self.title = (title or "").strip() or None
        self.author = (author or "").strip() or None
        self.provider = provider
        self.when = when or now_ist()
        self.max_context_chars = max_context_chars

    def run(self) -> StudioResult:
        project = self.load()
        context = self.build_context(project)
        raw = self.ask(context)
        plan = self.validate(raw, project, context)
        plan.notes = (project.notes() + plan.notes)[:MAX_NOTES]
        return self.build_outputs(project, plan)

    def load(self) -> Project:
        return source_for(self.uploads).load()

    def build_context(self, project) -> ProjectContext:
        return build_context(project, self.max_context_chars)

    def ask(self, context) -> dict:
        provider = self.provider or get_provider()
        try:
            return provider.run(self.prompt, context.text, self.title)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"The model could not complete the task: {str(e)[:300]}")

    def validate(self, raw, project, context) -> Plan:
        return validate_plan(raw, project, context, self.title)

    def build_outputs(self, project, plan) -> StudioResult:
        return build_outputs(project, plan, self.prompt, self.author, self.when)
