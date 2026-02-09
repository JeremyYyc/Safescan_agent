from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List
from datetime import datetime
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value).strip())


def _safe_paragraph(text: Any, style: ParagraphStyle) -> Paragraph:
    escaped = _safe_text(text).replace("\n", "<br/>")
    return Paragraph(escaped, style)


def _list_to_paragraph(items: Iterable[Any], style: ParagraphStyle, empty_label: str = "N/A") -> Paragraph:
    if not items:
        return Paragraph(_safe_text(empty_label), style)
    lines = [f"• {_safe_text(item)}" for item in items if str(item).strip()]
    if not lines:
        return Paragraph(_safe_text(empty_label), style)
    return Paragraph("<br/>".join(lines), style)


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=base["Title"], fontSize=18, spaceAfter=4),
        "subtitle": ParagraphStyle(
            "ReportSubtitle", parent=base["BodyText"], fontSize=9, textColor=colors.HexColor("#6b7280"), spaceAfter=8
        ),
        "section": ParagraphStyle(
            "SectionTitle",
            parent=base["Heading2"],
            fontSize=14,
            spaceAfter=6,
            textColor=colors.HexColor("#1f2937"),
            keepWithNext=1,
        ),
        "card_title": ParagraphStyle("CardTitle", parent=base["Heading4"], fontSize=11, spaceAfter=4),
        "label": ParagraphStyle("Label", parent=base["Heading5"], fontSize=9, textColor=colors.HexColor("#4b4b4b")),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=10, leading=12),
        "score_note": ParagraphStyle(
            "ScoreNote",
            parent=base["BodyText"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#9ca3af"),
        ),
    }


def _key_value_table(rows: List[List[str]], font_size: int = 9, col_widths: List[int] | None = None) -> Table:
    table = Table(rows, colWidths=col_widths or [140, 380])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), font_size),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.whitesmoke, colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]
        )
    )
    return table


def _card_block(
    title: str | None,
    body: List[Any],
    styles: Dict[str, ParagraphStyle],
    *,
    background: colors.Color | None = None,
    border: colors.Color | None = None,
) -> Table:
    content = []
    if title:
        content.extend([Paragraph(_safe_text(title), styles["card_title"]), Spacer(1, 6)])
    content.extend(body)
    table = Table([[content]], colWidths=[520])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), background or colors.HexColor("#F7F4EE")),
                ("BOX", (0, 0), (-1, -1), 0.6, border or colors.HexColor("#E4D7B8")),
                ("INNERPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def _palette(key: str) -> tuple[colors.Color, colors.Color]:
    palette = {
        "risk": (colors.HexColor("#FDECEC"), colors.HexColor("#F3B9B9")),
        "recommendation": (colors.HexColor("#EAF7EF"), colors.HexColor("#B7E0C2")),
        "region": (colors.HexColor("#FFF4D6"), colors.HexColor("#F4D39B")),
        "comfort": (colors.HexColor("#EAF3FF"), colors.HexColor("#B7CFF2")),
        "compliance": (colors.HexColor("#F1F0FF"), colors.HexColor("#CEC7F2")),
        "action": (colors.HexColor("#EAF7EF"), colors.HexColor("#B7E0C2")),
        "limitations": (colors.HexColor("#FFF9E6"), colors.HexColor("#EED9A9")),
        "default": (colors.HexColor("#F7F4EE"), colors.HexColor("#E4D7B8")),
    }
    return palette.get(key, palette["default"])


def _section_title(text: str, color: colors.Color | None = None) -> Paragraph:
    style = _styles()["section"]
    if color is not None:
        style = ParagraphStyle("SectionTitleColor", parent=style, textColor=color)
    return Paragraph(_safe_text(text), style)


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        key = item.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _build_meta_rows(meta: Dict[str, Any]) -> List[List[str]]:
    if not isinstance(meta, dict):
        return [["Meta", "N/A"]]
    rows = []
    for key in ["home_type", "occupancy", "special_groups", "pets", "data_sources", "analysis_time"]:
        value = meta.get(key)
        if isinstance(value, list):
            value = ", ".join([str(item) for item in value if str(item).strip()])
        if value in (None, "", []):
            continue
        rows.append([key, str(value)])
    return rows


def render_report_pdf(report: Dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    styles = _styles()
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Safe-Scan Report",
        author="Safe-Scan",
    )

    story: List[Any] = []
    title = report.get("title") if isinstance(report, dict) else None
    story.append(Paragraph(_safe_text(title or "Home Safety Report"), styles["title"]))
    story.append(
        Paragraph(
            _safe_text(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"),
            styles["subtitle"],
        )
    )

    meta_rows = _build_meta_rows(report.get("meta", {}))
    if meta_rows:
        story.append(KeepTogether([_section_title("Overview"), _key_value_table(meta_rows)]))
        story.append(Spacer(1, 8))

    scores = report.get("scores", {})
    story.append(_section_title("Scores"))
    if isinstance(scores, dict):
        dimensions = scores.get("dimensions")
        if not isinstance(dimensions, dict):
            dimensions = {}
        headers = ["overall", *[str(key) for key in dimensions.keys()]]
        values = [str(scores.get("overall", "N/A")), *[str(value) for value in dimensions.values()]]
        matrix = [headers, values] if headers else [["overall"], [str(scores.get("overall", "N/A"))]]
        col_count = max(len(matrix[0]), 1)
        col_width = max(60, int(520 / col_count))
        col_widths = [col_width] * col_count
        story.append(KeepTogether([_key_value_table(matrix, font_size=10, col_widths=col_widths)]))
        story.append(Spacer(1, 4))
        story.append(Paragraph("Rationale (summary)", styles["label"]))
        story.append(_safe_paragraph(scores.get("rationale", "N/A"), styles["score_note"]))
    else:
        story.append(_safe_paragraph("N/A", styles["score_note"]))
    story.append(Spacer(1, 8))

    bg, br = _palette("risk")
    story.append(_section_title("Top Risks", colors.HexColor("#b45309")))
    top_risks = report.get("top_risks", [])
    if isinstance(top_risks, list) and top_risks:
        items = [
            f"{risk.get('risk', 'Risk')} ({risk.get('priority', 'N/A')}) - {risk.get('impact', 'N/A')}"
            for risk in top_risks
            if isinstance(risk, dict)
        ]
        items = _dedupe(items)
        risk_card = _card_block(None, [_list_to_paragraph(items, styles["body"])], styles, background=bg, border=br)
        story.append(risk_card)
    else:
        risk_card = _card_block(None, [_safe_paragraph("N/A", styles["body"])], styles, background=bg, border=br)
        story.append(risk_card)
    story.append(Spacer(1, 8))

    bg, br = _palette("recommendation")
    story.append(_section_title("Recommendations", colors.HexColor("#2f6f3e")))
    recs = report.get("recommendations", {})
    actions = recs.get("actions") if isinstance(recs, dict) else []
    if isinstance(actions, list) and actions:
        items = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            items.append(
                f"{action.get('action', 'Action')} - {action.get('priority', 'N/A')} / "
                f"{action.get('difficulty', 'N/A')} / {action.get('budget', 'N/A')}"
            )
        items = _dedupe(items)
        rec_card = _card_block(None, [_list_to_paragraph(items, styles["body"])], styles, background=bg, border=br)
        story.append(rec_card)
    else:
        rec_card = _card_block(None, [_safe_paragraph("N/A", styles["body"])], styles, background=bg, border=br)
        story.append(rec_card)
    story.append(Spacer(1, 8))

    story.append(_section_title("Regions", colors.HexColor("#a16207")))
    regions = report.get("regions", [])
    if isinstance(regions, list) and regions:
        for idx, region in enumerate(regions, start=1):
            if not isinstance(region, dict):
                continue
            region_names = region.get("regionName") or []
            if isinstance(region_names, list):
                name = ", ".join([str(item) for item in region_names if str(item).strip()]) or f"Region {idx}"
            else:
                name = str(region_names) if region_names else f"Region {idx}"
            card_body = [
                Paragraph("Potential Hazards", styles["label"]),
                _list_to_paragraph(region.get("potentialHazards", []), styles["body"]),
                Paragraph("Special Hazards", styles["label"]),
                _list_to_paragraph(region.get("specialHazards", []), styles["body"]),
                Paragraph("Color & Lighting", styles["label"]),
                _list_to_paragraph(region.get("colorAndLightingEvaluation", []), styles["body"]),
                Paragraph("Suggestions", styles["label"]),
                _list_to_paragraph(region.get("suggestions", []), styles["body"]),
            ]
            bg, br = _palette("region")
            story.append(KeepTogether([_card_block(name, card_body, styles, background=bg, border=br), Spacer(1, 6)]))
    else:
        story.append(_safe_paragraph("N/A", styles["body"]))

    story.append(_section_title("Comfort", colors.HexColor("#1d4ed8")))
    comfort = report.get("comfort", {})
    bg, br = _palette("comfort")
    story.append(
        _card_block(
            None,
            [
                Paragraph("Observations", styles["label"]),
                _list_to_paragraph(comfort.get("observations", []) if isinstance(comfort, dict) else [], styles["body"]),
                Paragraph("Suggestions", styles["label"]),
                _list_to_paragraph(comfort.get("suggestions", []) if isinstance(comfort, dict) else [], styles["body"]),
            ],
            styles,
            background=bg,
            border=br,
        )
    )
    story.append(Spacer(1, 8))

    story.append(_section_title("Compliance", colors.HexColor("#6d28d9")))
    compliance = report.get("compliance", {})
    checklist = compliance.get("checklist") if isinstance(compliance, dict) else []
    checklist_items = [
        f"{item.get('item', 'Item')} ({item.get('priority', 'N/A')})"
        for item in checklist
        if isinstance(item, dict)
    ]
    bg, br = _palette("compliance")
    story.append(
        _card_block(
            None,
            [
                Paragraph("Notes", styles["label"]),
                _list_to_paragraph(compliance.get("notes", []) if isinstance(compliance, dict) else [], styles["body"]),
                Paragraph("Checklist", styles["label"]),
                _list_to_paragraph(checklist_items, styles["body"]),
            ],
            styles,
            background=bg,
            border=br,
        )
    )
    story.append(Spacer(1, 8))

    story.append(_section_title("Action Plan", colors.HexColor("#2f6f3e")))
    action_plan = report.get("action_plan", [])
    action_items = [
        f"{item.get('action', 'Action')} ({item.get('priority', 'N/A')}) - {item.get('timeline', 'N/A')}"
        for item in action_plan
        if isinstance(item, dict)
    ]
    bg, br = _palette("action")
    story.append(
        _card_block(
            None,
            [_list_to_paragraph(action_items, styles["body"])],
            styles,
            background=bg,
            border=br,
        )
    )

    story.append(_section_title("Limitations", colors.HexColor("#92400e")))
    bg, br = _palette("limitations")
    story.append(
        _card_block(
            None,
            [_list_to_paragraph(report.get("limitations", []), styles["body"])],
            styles,
            background=bg,
            border=br,
        )
    )

    doc.build(story)
