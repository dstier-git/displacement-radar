from __future__ import annotations

import html
import re

COLORS = ["#7dd3fc", "#a78bfa", "#f9a8d4", "#fde68a", "#86efac", "#fb7185", "#67e8f9", "#c4b5fd"]


def render_markdown_report(markdown: str) -> str:
    """Render the app's constrained markdown report to safe, self-contained HTML.

    This intentionally supports only the subset emitted by reports.py: headings,
    paragraphs, bullets, markdown tables, bold spans, and Mermaid code fences.
    Mermaid blocks are rendered server-side into HTML/CSS graphs so the report
    works even when CDN JavaScript is blocked or unavailable.
    """

    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    in_list = False

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            if in_list:
                output.append("</ul>")
                in_list = False
            index += 1
            continue

        if stripped == "```mermaid":
            if in_list:
                output.append("</ul>")
                in_list = False
            index += 1
            mermaid_lines: list[str] = []
            while index < len(lines) and lines[index].strip() != "```":
                mermaid_lines.append(lines[index])
                index += 1
            output.append(_render_mermaid_block("\n".join(mermaid_lines)))
            index += 1
            continue

        if stripped.startswith("|") and "|" in stripped[1:]:
            if in_list:
                output.append("</ul>")
                in_list = False
            table_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index].strip())
                index += 1
            output.append(_render_table(table_lines))
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            if in_list:
                output.append("</ul>")
                in_list = False
            level = len(heading_match.group(1))
            output.append(f"<h{level}>{_inline(heading_match.group(2))}</h{level}>")
            index += 1
            continue

        if stripped.startswith("- "):
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{_inline(stripped[2:])}</li>")
            index += 1
            continue

        if in_list:
            output.append("</ul>")
            in_list = False
        output.append(f"<p>{_inline(stripped)}</p>")
        index += 1

    if in_list:
        output.append("</ul>")
    return "\n".join(output)


def _render_table(lines: list[str]) -> str:
    if not lines:
        return ""
    rows = [[cell.strip() for cell in line.strip("|").split("|")] for line in lines]
    header = rows[0]
    body = rows[2:] if len(rows) > 1 and set(rows[1][0]) <= {"-", ":"} else rows[1:]
    parts = ["<div class=\"table-wrap\"><table>", "<thead><tr>"]
    parts.extend(f"<th>{_inline(cell)}</th>" for cell in header)
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>")
        parts.extend(f"<td>{_inline(cell)}</td>" for cell in row)
        parts.append("</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


def _render_mermaid_block(code: str) -> str:
    stripped = code.strip()
    if stripped.startswith("flowchart"):
        return _render_flowchart(stripped)
    if stripped.startswith("xychart-beta"):
        return _render_xy_chart(stripped)
    if stripped.startswith("pie"):
        return _render_pie_chart(stripped)
    escaped = html.escape(stripped)
    return f'<pre class="rendered-graph raw-graph">{escaped}</pre>'


def _render_flowchart(code: str) -> str:
    labels: dict[str, str] = {}
    edges: list[tuple[str, str]] = []
    for line in code.splitlines()[1:]:
        if "-->" not in line:
            continue
        left, right = [part.strip() for part in line.split("-->", 1)]
        src_id, src_label = _parse_mermaid_node(left)
        dst_id, dst_label = _parse_mermaid_node(right)
        labels.setdefault(src_id, src_label or src_id)
        labels.setdefault(dst_id, dst_label or dst_id)
        edges.append((src_id, dst_id))

    if not edges:
        return '<div class="rendered-graph flow-graph empty-graph">No landscape graph data yet.</div>'

    rows = []
    for source, target in edges:
        rows.append(
            '<div class="flow-edge">'
            f'<span class="flow-node">{html.escape(labels[source])}</span>'
            '<span class="flow-arrow">→</span>'
            f'<span class="flow-node target">{html.escape(labels[target])}</span>'
            '</div>'
        )
    return '<div class="rendered-graph flow-graph">' + "".join(rows) + "</div>"


def _parse_mermaid_node(value: str) -> tuple[str, str | None]:
    match = re.match(r"^([A-Za-z0-9_]+)(?:\[(.*)\])?$", value.strip())
    if not match:
        safe_id = re.sub(r"\W+", "_", value.strip()) or "node"
        return safe_id, value.strip()
    return match.group(1), match.group(2)


def _render_xy_chart(code: str) -> str:
    title = _extract_quoted_line(code, "title") or "Last 30 days movement"
    labels = _extract_axis_labels(code)
    bars = _extract_number_list(code, "bar")
    line = _extract_number_list(code, "line")
    count = max(len(labels), len(bars), len(line))
    if count == 0:
        return '<div class="rendered-graph empty-graph">No monthly movement data yet.</div>'
    labels = _pad(labels, count, "Unknown")
    bars = _pad_numbers(bars, count)
    line = _pad_numbers(line, count)
    max_value = max([1, *bars, *line])

    rows = [f'<h3 class="graph-title">{html.escape(title)}</h3>', '<div class="bar-chart">']
    for label, bar_value, line_value in zip(labels, bars, line, strict=False):
        bar_width = round((bar_value / max_value) * 100)
        line_width = round((line_value / max_value) * 100)
        rows.append(
            '<div class="bar-row">'
            f'<div class="bar-label">{html.escape(label)}</div>'
            '<div class="bar-track">'
            f'<div class="bar-fill signal-fill" style="width:{bar_width}%"><span>{bar_value} signals</span></div>'
            f'<div class="bar-fill opportunity-fill" style="width:{line_width}%"><span>{line_value} opps</span></div>'
            '</div></div>'
        )
    rows.append('</div><div class="graph-legend"><span class="legend-dot signal"></span>Signals <span class="legend-dot opportunity"></span>Opportunities</div>')
    return '<div class="rendered-graph xy-graph">' + "".join(rows) + '</div>'


def _render_pie_chart(code: str) -> str:
    title_match = re.match(r"pie title\s+(.+)", code.splitlines()[0].strip())
    title = title_match.group(1) if title_match else "Signal mix"
    slices: list[tuple[str, int]] = []
    for line in code.splitlines()[1:]:
        match = re.match(r'\s*"(.+?)"\s*:\s*(\d+)', line)
        if match:
            slices.append((match.group(1), int(match.group(2))))
    if not slices:
        slices = [("No signals", 1)]
    total = max(sum(value for _, value in slices), 1)
    cursor = 0.0
    segments: list[str] = []
    legend: list[str] = []
    for index, (label, value) in enumerate(slices):
        color = COLORS[index % len(COLORS)]
        start = cursor
        cursor += (value / total) * 100
        segments.append(f"{color} {start:.2f}% {cursor:.2f}%")
        legend.append(
            '<div class="pie-legend-row">'
            f'<span class="legend-dot" style="background:{color}"></span>'
            f'<span>{html.escape(label)}</span><strong>{value}</strong>'
            '</div>'
        )
    style = "background: conic-gradient(" + ", ".join(segments) + ")"
    return (
        '<div class="rendered-graph pie-graph">'
        f'<h3 class="graph-title">{html.escape(title)}</h3>'
        '<div class="pie-layout">'
        f'<div class="pie-chart" style="{style}"></div>'
        '<div class="pie-legend">' + "".join(legend) + '</div>'
        '</div></div>'
    )


def _extract_quoted_line(code: str, prefix: str) -> str | None:
    match = re.search(rf'{prefix}\s+"(.+?)"', code)
    return match.group(1) if match else None


def _extract_axis_labels(code: str) -> list[str]:
    match = re.search(r"x-axis\s+\[(.+?)\]", code)
    if not match:
        return []
    return [item.strip().strip('"') for item in match.group(1).split(",")]


def _extract_number_list(code: str, prefix: str) -> list[int]:
    match = re.search(rf"{prefix}\s+\[(.*?)\]", code)
    if not match:
        return []
    values = []
    for item in match.group(1).split(","):
        item = item.strip()
        if item:
            values.append(int(item))
    return values


def _pad(values: list[str], count: int, default: str) -> list[str]:
    return values + [default] * (count - len(values))


def _pad_numbers(values: list[int], count: int) -> list[int]:
    return values + [0] * (count - len(values))


def _inline(value: str) -> str:
    escaped = html.escape(value)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
