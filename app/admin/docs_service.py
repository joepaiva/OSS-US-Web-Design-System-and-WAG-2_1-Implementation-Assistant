"""In-app documentation rendering for the admin shell (chassis v0.8).

Surfaces a small, whitelisted set of chassis Markdown documents (README,
How It Works, User Manual, Security Self-Audit) inside the admin shell at
`/admin/docs`, rendered to HTML.

Security posture:
  - **No arbitrary file access.** Only the slugs in `_DOC_REGISTRY` are
    served; the requested slug is looked up in that dict, never joined onto
    a filesystem path. Path traversal is structurally impossible.
  - **HTML is escaped before rendering.** The Markdown renderer escapes all
    source text first, then re-introduces a safe, fixed subset of tags. The
    documents are operator-trusted (bundled in the image), but escaping
    keeps the renderer safe even if that ever changes.

The renderer is a deliberately small subset of Markdown — enough for the
chassis docs (headings, paragraphs, lists, tables, fenced/inline code,
blockquotes, links, bold/italic, horizontal rules). It is NOT a general
CommonMark implementation; that would warrant a real dependency.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path

# Chassis root = parent of the `app/` package directory.
_CHASSIS_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass(frozen=True)
class DocEntry:
    slug: str
    title: str
    summary: str
    relative_path: str  # relative to chassis root; chassis-controlled, not user input


# Whitelist. Only these documents are ever served. The slug is the lookup
# key — it is never used to build a filesystem path.
_DOC_REGISTRY: dict[str, DocEntry] = {
    "how-it-works": DocEntry(
        "how-it-works",
        "How It Works",
        "Operator-facing overview of what the application provides and how the parts fit together.",
        "docs/HOW-IT-WORKS.md",
    ),
    "user-manual": DocEntry(
        "user-manual",
        "User Manual",
        "End-user guide: accounts, sign-in, profile, and the admin shell.",
        "docs/USER-MANUAL.md",
    ),
    "security-self-audit": DocEntry(
        "security-self-audit",
        "Security Self-Audit (FISMA Moderate)",
        "NIST 800-53 control mapping for the chassis at the FISMA Moderate baseline.",
        "docs/SECURITY-SELF-AUDIT.md",
    ),
    "readme": DocEntry(
        "readme",
        "README",
        "Chassis overview, tech stack, and developer quickstart.",
        "README.md",
    ),
}


def list_docs() -> list[DocEntry]:
    """All available documents in display order."""
    return list(_DOC_REGISTRY.values())


def get_doc(slug: str) -> DocEntry | None:
    """Look up a doc by slug. Returns None for unknown slugs."""
    return _DOC_REGISTRY.get(slug)


def load_doc_html(entry: DocEntry) -> str:
    """Read the document from disk and render it to safe HTML.

    Raises FileNotFoundError if the bundled file is missing (a packaging
    error, surfaced to the operator as a 'document unavailable' message).
    """
    path = _CHASSIS_ROOT / entry.relative_path
    text = path.read_text(encoding="utf-8")
    return render_markdown(text)


# ─── Minimal, safe Markdown → HTML ──────────────────────────────────────

_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_ITALIC = re.compile(r"(?<![*])\*(?!\s)([^*]+?)\*(?![*])")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_ULIST = re.compile(r"^[-*]\s+(.*)$")
_OLIST = re.compile(r"^\d+\.\s+(.*)$")
_HR = re.compile(r"^(-{3,}|\*{3,})$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)+\|?$")


def _inline(text: str) -> str:
    """Apply inline formatting to an already-HTML-escaped line."""
    text = _INLINE_CODE.sub(r"<code>\1</code>", text)
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    text = _ITALIC.sub(r"<em>\1</em>", text)

    def _link_sub(m: re.Match[str]) -> str:
        label, href = m.group(1), m.group(2)
        # Only allow safe schemes; everything else renders as plain label.
        if href.startswith(("http://", "https://", "/", "#", "mailto:")):
            return f'<a href="{href}">{label}</a>'
        return label

    text = _LINK.sub(_link_sub, text)
    return text


def _split_table_row(line: str) -> list[str]:
    cells = line.strip().strip("|").split("|")
    return [c.strip() for c in cells]


def render_markdown(src: str) -> str:
    """Render a safe subset of Markdown to HTML.

    Source is HTML-escaped first; only a fixed set of block/inline
    constructs are re-introduced. Unknown constructs degrade to escaped
    text inside a paragraph.
    """
    lines = src.replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    # State for paragraph buffering.
    para: list[str] = []

    def flush_para() -> None:
        if para:
            joined = " ".join(para)
            out.append(f"<p>{_inline(joined)}</p>")
            para.clear()

    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        # Fenced code block.
        if stripped.startswith("```"):
            flush_para()
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(html.escape(lines[i]))
                i += 1
            i += 1  # skip closing fence
            out.append("<pre><code>" + "\n".join(code_lines) + "</code></pre>")
            continue

        # Blank line ends a paragraph.
        if stripped == "":
            flush_para()
            i += 1
            continue

        escaped = html.escape(stripped)

        # Horizontal rule.
        if _HR.match(stripped):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        # Heading.
        m = _HEADING.match(stripped)
        if m:
            flush_para()
            level = len(m.group(1))
            text = _inline(html.escape(m.group(2)))
            out.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # Table: header row followed by a separator row.
        if stripped.startswith("|") and i + 1 < n and _TABLE_SEP.match(lines[i + 1].strip()):
            flush_para()
            header = _split_table_row(stripped)
            out.append('<table class="usa-table usa-table--borderless">')
            out.append("<thead><tr>")
            for cell in header:
                out.append(f"<th scope=\"col\">{_inline(html.escape(cell))}</th>")
            out.append("</tr></thead><tbody>")
            i += 2  # skip header + separator
            while i < n and lines[i].strip().startswith("|"):
                row = _split_table_row(lines[i].strip())
                out.append("<tr>")
                for cell in row:
                    out.append(f"<td>{_inline(html.escape(cell))}</td>")
                out.append("</tr>")
                i += 1
            out.append("</tbody></table>")
            continue

        # Blockquote.
        if stripped.startswith(">"):
            flush_para()
            quote_lines: list[str] = []
            while i < n and lines[i].strip().startswith(">"):
                quote_lines.append(html.escape(lines[i].strip().lstrip(">").strip()))
                i += 1
            inner = _inline(" ".join(quote_lines))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # Unordered list.
        if _ULIST.match(stripped):
            flush_para()
            out.append("<ul>")
            while i < n and _ULIST.match(lines[i].strip()):
                item = _ULIST.match(lines[i].strip()).group(1)  # type: ignore[union-attr]
                out.append(f"<li>{_inline(html.escape(item))}</li>")
                i += 1
            out.append("</ul>")
            continue

        # Ordered list.
        if _OLIST.match(stripped):
            flush_para()
            out.append("<ol>")
            while i < n and _OLIST.match(lines[i].strip()):
                item = _OLIST.match(lines[i].strip()).group(1)  # type: ignore[union-attr]
                out.append(f"<li>{_inline(html.escape(item))}</li>")
                i += 1
            out.append("</ol>")
            continue

        # Default: accumulate into a paragraph.
        para.append(escaped)
        i += 1

    flush_para()
    return "\n".join(out)
