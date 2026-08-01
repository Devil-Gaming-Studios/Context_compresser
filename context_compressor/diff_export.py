"""
Export a CompressionReport's diff as a standalone Markdown or HTML
report -- useful for sharing "here's exactly what got cut and why"
outside of the live UI.
"""

import html as _html
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .compressor import CompressionReport


def to_markdown(report: "CompressionReport", title: str = "Context Compression Report") -> str:
    lines = [
        f"# {title}",
        "",
        f"**{report.summary()}**",
        "",
        "## Notes",
        "",
    ]
    for n in report.notes:
        lines.append(f"- {n}")
    lines.append("")
    lines.append("## Diff")
    lines.append("")
    lines.append("`+` kept · `-` dropped")
    lines.append("")
    lines.append("```diff")
    for d in report.diff_lines:
        prefix = "+ " if d.kept else "- "
        for sub in (d.text.splitlines() or [""]):
            lines.append(f"{prefix}{sub}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
  h1 {{ font-size: 1.4rem; }}
  .summary {{ background: #f4f4f5; padding: 0.75rem 1rem; border-radius: 6px; font-size: 0.95rem; }}
  ul.notes {{ font-size: 0.9rem; color: #444; }}
  .diff {{ font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.85rem; white-space: pre-wrap;
           border: 1px solid #e2e2e2; border-radius: 6px; overflow: hidden; }}
  .kept {{ background: #eafaf0; color: #1a5c33; padding: 1px 8px; display: block; }}
  .dropped {{ background: #fdeceb; color: #8c2c22; text-decoration: line-through; padding: 1px 8px; display: block; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="summary">{summary}</div>
<h2>Notes</h2>
<ul class="notes">{notes}</ul>
<h2>Diff</h2>
<div class="diff">{diff}</div>
</body>
</html>
"""


def to_html(report: "CompressionReport", title: str = "Context Compression Report") -> str:
    notes_html = "".join(f"<li>{_html.escape(n)}</li>" for n in report.notes)
    diff_rows = []
    for d in report.diff_lines:
        cls = "kept" if d.kept else "dropped"
        for sub in (d.text.splitlines() or [""]):
            diff_rows.append(f'<span class="{cls}">{_html.escape(sub) or "&nbsp;"}</span>')
    diff_html = "".join(diff_rows)
    return _HTML_TEMPLATE.format(
        title=_html.escape(title),
        summary=_html.escape(report.summary()),
        notes=notes_html,
        diff=diff_html,
    )


def write_report(report: "CompressionReport", path: str, title: str = "Context Compression Report"):
    """Write a Markdown or HTML report to `path`, format inferred from
    the file extension (.md/.markdown -> Markdown, anything else -> HTML)."""
    if path.lower().endswith((".md", ".markdown")):
        content = to_markdown(report, title)
    else:
        content = to_html(report, title)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path
