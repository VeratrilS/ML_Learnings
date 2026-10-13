"""
Task Studio: turning an upload into a normalized in-memory Project.

SYSTEM DESIGN CONCEPT: Strategy
ProjectSource is the interface; ZipSource (one .zip) and FilesSource (one file, many files or a whole
folder sent with relative paths) are interchangeable strategies. Both produce the same Project, so the
rest of the pipeline never cares how the files arrived. A new input type (e.g. a Git URL) is one class.
"""
import io
import posixpath
import re
import zipfile
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

MAX_EXTRACTED_BYTES = 40 * 1024 * 1024  # zip-bomb guard: total uncompressed size
MAX_FILES = 5000
MAX_PATH = 400

# Dropped entirely (not sent to the model, not in the output zip).
EXCLUDED_DIRS = {"node_modules", ".git", "dist", "build", "__pycache__", ".venv", "venv"}
JUNK_DIRS = {"__MACOSX"}
JUNK_FILES = {".DS_Store", "Thumbs.db", "desktop.ini"}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff", ".psd",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".odt",
    ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".war", ".whl",
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib", ".class", ".pyc", ".pyo", ".bin", ".dat",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".sqlite", ".db", ".pkl", ".pickle", ".npy", ".npz", ".h5", ".hdf5", ".pt", ".pth", ".onnx", ".parquet",
}

_DRIVE = re.compile(r"^[A-Za-z]:")


class SourceError(ValueError):
    """The upload can't be used (bad zip, nothing usable). Maps to HTTP 400."""


class ProjectTooLarge(SourceError):
    """The upload expands past our limits. Maps to HTTP 413."""


@dataclass
class Project:
    files: dict = field(default_factory=dict)      # relative posix path -> bytes
    rejected: list = field(default_factory=list)   # unsafe paths we refused (absolute, "..", ...)
    excluded: list = field(default_factory=list)   # paths under node_modules/, .git/, ... (dropped)

    def notes(self):
        out = []
        if self.rejected:
            shown = ", ".join(self.rejected[:5]) + (" ..." if len(self.rejected) > 5 else "")
            out.append(f"Ignored {len(self.rejected)} upload path(s) that were absolute or pointed outside the project: {shown}")
        if self.excluded:
            dirs = sorted({next(p for p in path.split("/") if p in EXCLUDED_DIRS) for path in self.excluded})
            out.append(f"Left out {len(self.excluded)} file(s) under {', '.join(d + '/' for d in dirs)} "
                       "(not sent to the model and not included in the output zip).")
        return out


# ---------------- path + content helpers ----------------
def safe_path(name):
    """Normalise an upload path to a relative posix path, or return None if it is unsafe.

    Backslashes become slashes, "." and empty parts are dropped. Absolute paths, drive letters
    and any ".." component are rejected rather than repaired.
    """
    if not isinstance(name, str):
        return None
    path = name.replace("\\", "/").strip()
    if not path or path.startswith("/") or _DRIVE.match(path) or "\x00" in path or len(path) > MAX_PATH:
        return None
    parts = [p for p in path.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts) or any(p != p.strip() or any(ord(c) < 32 for c in p) for p in parts):
        return None
    return "/".join(parts)


def is_junk(path):
    parts = path.split("/")
    return parts[-1] in JUNK_FILES or parts[-1].startswith("._") or any(p in JUNK_DIRS for p in parts)


def is_excluded(path):
    return any(p in EXCLUDED_DIRS for p in path.split("/")[:-1])


def is_text(path, data):
    """Heuristic: known binary extension, a NUL byte, or invalid UTF-8 means binary."""
    if posixpath.splitext(path.lower())[1] in BINARY_EXTENSIONS:
        return False
    if b"\x00" in data[:8192]:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


# ---------------- strategies ----------------
class ProjectSource(ABC):
    """Strategy interface: something that can produce a Project."""

    @abstractmethod
    def entries(self):
        """Yields (raw_name, bytes) pairs."""

    def load(self) -> Project:
        project = Project()
        for raw_name, data in self.entries():
            path = safe_path(raw_name)
            if path is None:
                project.rejected.append(str(raw_name)[:120])
                continue
            if is_junk(path):
                continue
            if is_excluded(path):
                project.excluded.append(path)
                continue
            project.files[path] = data
            if len(project.files) > MAX_FILES:
                raise ProjectTooLarge(f"The project has more than {MAX_FILES} files.")
        if not project.files:
            raise SourceError("No usable files found in the upload.")
        return project


class ZipSource(ProjectSource):
    """One uploaded .zip, extracted in memory (zip-slip safe: names go through safe_path)."""

    def __init__(self, data: bytes):
        self.data = data

    def entries(self):
        try:
            zf = zipfile.ZipFile(io.BytesIO(self.data))
        except (zipfile.BadZipFile, OSError) as e:
            raise SourceError(f"Could not open the zip file ({e}).")
        total = 0
        with zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                if info.flag_bits & 0x1:
                    raise SourceError("Password-protected zip files are not supported.")
                with zf.open(info) as fh:
                    data = fh.read(MAX_EXTRACTED_BYTES - total + 1)
                total += len(data)
                if total > MAX_EXTRACTED_BYTES:
                    raise ProjectTooLarge(f"The zip expands to more than {MAX_EXTRACTED_BYTES // (1024 * 1024)} MB.")
                yield info.filename, data


class FilesSource(ProjectSource):
    """Loose files; for folder uploads each filename is its relative path (e.g. "proj/src/main.py")."""

    def __init__(self, uploads):
        self.uploads = list(uploads)

    def entries(self):
        yield from self.uploads


def source_for(uploads) -> ProjectSource:
    """Factory: exactly one .zip -> ZipSource, anything else -> FilesSource."""
    uploads = list(uploads)
    if len(uploads) == 1 and str(uploads[0][0]).lower().endswith(".zip"):
        return ZipSource(uploads[0][1])
    return FilesSource(uploads)
