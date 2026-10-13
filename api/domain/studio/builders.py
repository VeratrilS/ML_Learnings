"""
Task Studio: building the outputs.

SYSTEM DESIGN CONCEPT: Builder
ZipBuilder and PdfReportBuilder assemble their product step by step (apply changes, add files /
add sections, a table) and only produce bytes in build(). The pipeline decides what goes in;
the builders only know how to lay it out.
"""
import io
import re
import unicodedata
import zipfile
from datetime import datetime
from functools import lru_cache

# ---------------- zip ----------------
class ZipBuilder:
    """Project files + changes -> deterministic zip (sorted paths, one fixed timestamp)."""

    def __init__(self, files: dict, when: datetime = None):
        self.files = dict(files)
        self.when = when or datetime.now()

    def apply(self, changes):
        """`changes` items need .path, .action ("create" | "update" | "delete") and .data (bytes)."""
        for c in changes:
            if c.action == "delete":
                self.files.pop(c.path, None)
            else:
                self.files[c.path] = c.data
        return self

    def has(self, path):
        low = path.lower()
        return any(p.lower() == low for p in self.files)

    def add(self, path, data):
        self.files[path] = data.encode("utf-8") if isinstance(data, str) else data
        return self

    def build(self) -> bytes:
        stamp = max(self.when.timetuple()[:6], (1980, 1, 1, 0, 0, 0))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(self.files):
                info = zipfile.ZipInfo(path, date_time=stamp)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                zf.writestr(info, self.files[path])
        return buf.getvalue()


# ---------------- pdf ----------------
_LATIN1_MAP = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "–": "-", "—": "-", "―": "-", "−": "-", "‐": "-", "‑": "-",
    "…": "...", "•": "-", "●": "-", "▪": "-", "‣": "-", "⁃": "-", "·": "-",
    "→": "->", "←": "<-", "⇒": "=>", "↔": "<->", "≤": "<=", "≥": ">=", "≠": "!=",
    "≈": "~", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ", " ": " ",
    "​": "", "‌": "", "‍": "", "﻿": "", "✓": "[x]", "✔": "[x]", "✗": "[ ]",
    "™": "(TM)", "€": "EUR", "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Œ": "OE", "œ": "oe",
}
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def latin1(text) -> str:
    """Make any text safe for the PDF core fonts: map typographic characters, drop the rest."""
    text = str(text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    out = []
    for ch in text:
        if ch in _LATIN1_MAP:
            out.append(_LATIN1_MAP[ch])
        elif ord(ch) < 256:
            out.append(ch)
        else:  # e.g. accented letters outside latin-1 -> base letter; emoji and CJK -> dropped
            out.append("".join(c for c in unicodedata.normalize("NFKD", ch) if ord(c) < 256 and not unicodedata.combining(c)))
    return _CTRL.sub("", "".join(out))


def _inline(text):
    """Strip Markdown emphasis the core fonts can't show."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    return text.replace("`", "")


def text_blocks(text):
    """Split a section body into ("para" | "bullet" | "subhead" | "code", payload) blocks."""
    para, code, in_code = [], [], False
    for line in latin1(text).split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                yield "code", code
                code, in_code = [], False
            else:
                if para:
                    yield "para", " ".join(para)
                    para = []
                in_code = True
            continue
        if in_code:
            code.append(line.rstrip())
            continue
        bullet = re.match(r"^(?:[-*+]|\d+[.)])\s+(.*)$", stripped)
        subhead = re.match(r"^#{1,6}\s+(.*)$", stripped)
        if not stripped or bullet or subhead:
            if para:
                yield "para", " ".join(para)
                para = []
            if bullet:
                yield "bullet", (stripped if stripped[0].isdigit() else bullet.group(1))
            elif subhead:
                yield "subhead", subhead.group(1)
            continue
        para.append(stripped)
    if in_code and code:
        yield "code", code
    if para:
        yield "para", " ".join(para)


@lru_cache(maxsize=1)
def _report_pdf_class():
    """fpdf2 is imported on first use so it doesn't slow every cold start of the API."""
    from fpdf import FPDF

    class ReportPDF(FPDF):
        doc_title = ""

        def header(self):
            if self.page_no() > 1:
                self.set_font("Helvetica", "", 8)
                self.set_text_color(130, 130, 130)
                self.cell(0, 6, self.doc_title[:110], new_x="LMARGIN", new_y="NEXT")
                self.set_draw_color(220, 220, 220)
                self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
                self.ln(4)
                self.set_text_color(0, 0, 0)

        def footer(self):
            self.set_y(-14)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(130, 130, 130)
            self.cell(0, 8, f"Page {self.page_no()} of {{nb}}", align="C")
            self.set_text_color(0, 0, 0)

    return ReportPDF


class PdfReportBuilder:
    """Title page, then numbered sections; paragraphs, "- " bullets, a changes table and short code blocks."""
    MAX_CODE_LINES = 30
    LINE = 5.2

    def __init__(self, title, author=None, date=None, purpose="", summary=""):
        self.title = latin1(title).strip() or "Project report"
        self.pdf = _report_pdf_class()(format="A4")
        self.pdf.doc_title = self.title
        self.pdf.set_margins(20, 18, 20)
        self.pdf.set_auto_page_break(True, margin=20)
        self.pdf.set_title(self.title)
        if author:
            self.pdf.set_author(latin1(author))
        self.pdf.set_creator("Task Studio")
        self._section_no = 0
        self._title_page(latin1(author).strip(), date or datetime.now(), latin1(purpose).strip(), latin1(summary).strip())
        self.pdf.add_page()

    # -- building steps --
    def _title_page(self, author, date, purpose, summary):
        pdf = self.pdf
        pdf.add_page()
        pdf.set_y(72)
        pdf.set_font("Helvetica", "B", 24)
        pdf.multi_cell(0, 11, self.title, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 13)
        if author:
            pdf.multi_cell(0, 7, author, align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 11)
        pdf.set_text_color(90, 90, 90)
        pdf.cell(0, 7, f"{date.day} {date.strftime('%B %Y')}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        if purpose:
            pdf.ln(10)
            pdf.set_font("Helvetica", "I", 11)
            pdf.multi_cell(0, 6, purpose, align="C", new_x="LMARGIN", new_y="NEXT")
        if summary:
            pdf.ln(14)
            pdf.set_draw_color(210, 210, 210)
            pdf.line(pdf.l_margin + 30, pdf.get_y(), pdf.w - pdf.r_margin - 30, pdf.get_y())
            pdf.ln(6)
            pdf.set_font("Helvetica", "", 10.5)
            pdf.set_x(pdf.l_margin + 10)
            pdf.multi_cell(pdf.epw - 20, self.LINE, _inline(summary), align="J", new_x="LMARGIN", new_y="NEXT")

    def _heading(self, heading):
        pdf = self.pdf
        if pdf.get_y() > pdf.h - 50:
            pdf.add_page()
        self._section_no += 1
        pdf.ln(3 if pdf.get_y() < 35 else 7)
        pdf.set_font("Helvetica", "B", 13.5)
        pdf.multi_cell(0, 7, f"{self._section_no}. {latin1(heading)}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1.5)

    def section(self, heading, text, empty="Not provided."):
        pdf = self.pdf
        self._heading(heading)
        body = list(text_blocks(text or "")) or [("para", empty)]
        for kind, payload in body:
            if kind == "para":
                pdf.set_font("Helvetica", "", 10.5)
                pdf.multi_cell(0, self.LINE, _inline(payload), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
            elif kind == "bullet":
                pdf.set_font("Helvetica", "", 10.5)
                pdf.set_x(pdf.l_margin + 3)
                pdf.cell(5, self.LINE, "-")
                pdf.multi_cell(pdf.epw - 8, self.LINE, _inline(payload), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(0.8)
            elif kind == "subhead":
                pdf.ln(1)
                pdf.set_font("Helvetica", "B", 11)
                pdf.multi_cell(0, self.LINE + 0.6, _inline(payload), new_x="LMARGIN", new_y="NEXT")
                pdf.ln(0.5)
            elif kind == "code":
                self._code(payload)
        return self

    def _code(self, lines):
        pdf = self.pdf
        while lines and not lines[-1].strip():
            lines = lines[:-1]
        if len(lines) > self.MAX_CODE_LINES:
            lines = lines[:self.MAX_CODE_LINES] + ["..."]
        if not lines:
            return
        pdf.ln(0.5)
        pdf.set_font("Courier", "", 8.5)
        pdf.set_fill_color(244, 244, 244)
        pdf.multi_cell(0, 4.2, "\n".join(lines), fill=True, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2.5)

    def changes_table(self, heading, changes):
        """`changes` items need .path, .action and .why."""
        from fpdf.fonts import FontFace
        pdf = self.pdf
        self._heading(heading)
        if not changes:
            pdf.set_font("Helvetica", "", 10.5)
            pdf.multi_cell(0, self.LINE, "No project files were changed.", new_x="LMARGIN", new_y="NEXT")
            return self
        pdf.set_font("Helvetica", "", 9)
        pdf.set_draw_color(200, 200, 200)
        with pdf.table(col_widths=(34, 11, 55), line_height=4.8, text_align="LEFT", first_row_as_headings=True,
                       headings_style=FontFace(emphasis="BOLD", fill_color=(236, 236, 236)), padding=1.6) as table:
            row = table.row()
            for h in ("File", "Action", "Reason"):
                row.cell(h)
            for c in changes:
                row = table.row()
                row.cell(latin1(c.path))
                row.cell(c.action.capitalize())
                row.cell(_inline(latin1(c.why)) or "-")
        pdf.ln(2)
        return self

    def build(self) -> bytes:
        return bytes(self.pdf.output())
