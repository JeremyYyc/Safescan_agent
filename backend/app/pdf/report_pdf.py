from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, Iterable, List
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

PDF_FONT_NAME = "STSong-Light"
pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT_NAME))

LABELS = {
    "home_type": "住宅类型",
    "occupancy": "居住情况",
    "special_groups": "特殊人群",
    "pets": "宠物",
    "data_sources": "数据来源",
    "analysis_time": "分析时间",
    "overall": "综合评分",
    "fire": "消防安全",
    "electrical": "用电安全",
    "fall": "跌倒风险",
    "air_quality": "空气质量",
    "psychological": "心理舒适度",
    "high": "高",
    "medium": "中",
    "low": "低",
    "DIY": "可自行处理",
    "PRO": "建议专业人员处理",
}


def _label(value: Any) -> str:
    return LABELS.get(str(value), str(value))


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    return escape(str(value).strip())


def _safe_paragraph(text: Any, style: ParagraphStyle) -> Paragraph:
    escaped = _safe_text(text).replace("\n", "<br/>")
    return Paragraph(escaped, style)


def _list_to_paragraph(items: Iterable[Any], style: ParagraphStyle, empty_label: str = "暂无") -> Paragraph:
    if not items:
        return Paragraph(_safe_text(empty_label), style)
    lines = [f"• {_safe_text(item)}" for item in items if str(item).strip()]
    if not lines:
        return Paragraph(_safe_text(empty_label), style)
    return Paragraph("<br/>".join(lines), style)


def _styles() -> Dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("ReportTitle", parent=base["Title"], fontName=PDF_FONT_NAME, fontSize=18, spaceAfter=4),
        "subtitle": ParagraphStyle(
            "ReportSubtitle", parent=base["BodyText"], fontName=PDF_FONT_NAME, fontSize=9, textColor=colors.HexColor("#6b7280"), spaceAfter=8
        ),
        "section": ParagraphStyle(
            "SectionTitle",
            parent=base["Heading2"],
            fontName=PDF_FONT_NAME,
            fontSize=14,
            spaceAfter=6,
            textColor=colors.HexColor("#1f2937"),
            keepWithNext=1,
        ),
        "card_title": ParagraphStyle("CardTitle", parent=base["Heading4"], fontName=PDF_FONT_NAME, fontSize=11, spaceAfter=4),
        "label": ParagraphStyle("Label", parent=base["Heading5"], fontName=PDF_FONT_NAME, fontSize=9, textColor=colors.HexColor("#4b4b4b")),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontName=PDF_FONT_NAME, fontSize=10, leading=12),
        "score_note": ParagraphStyle(
            "ScoreNote",
            parent=base["BodyText"],
            fontName=PDF_FONT_NAME,
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
                ("FONTNAME", (0, 0), (-1, -1), PDF_FONT_NAME),
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
        return [["基本信息", "暂无"]]
    rows = []
    for key in ["home_type", "occupancy", "special_groups", "pets", "data_sources", "analysis_time"]:
        value = meta.get(key)
        if isinstance(value, list):
            value = ", ".join([str(item) for item in value if str(item).strip()])
        if value in (None, "", []):
            continue
        rows.append([_label(key), str(value)])
    return rows


def render_report_pdf(report: Dict[str, Any], output_path: BytesIO) -> None:
    styles = _styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
        title="Safe-Scan 家居安全报告",
        author="Safe-Scan",
    )

    story: List[Any] = []
    title = report.get("title") if isinstance(report, dict) else None
    story.append(Paragraph(_safe_text(title or "家居安全报告"), styles["title"]))
    story.append(
        Paragraph(
            _safe_text(f"生成时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y年%m月%d日 %H:%M')}（北京时间）"),
            styles["subtitle"],
        )
    )

    meta_rows = _build_meta_rows(report.get("meta", {}))
    if meta_rows:
        story.append(KeepTogether([_section_title("报告概览"), _key_value_table(meta_rows)]))
        story.append(Spacer(1, 8))

    scores = report.get("scores", {})
    story.append(_section_title("安全评分"))
    if isinstance(scores, dict):
        dimensions = scores.get("dimensions")
        if not isinstance(dimensions, dict):
            dimensions = {}
        headers = [_label("overall"), *[_label(key) for key in dimensions.keys()]]
        values = [str(scores.get("overall", "暂无")), *[str(value) for value in dimensions.values()]]
        matrix = [headers, values] if headers else [[_label("overall")], [str(scores.get("overall", "暂无"))]]
        col_count = max(len(matrix[0]), 1)
        col_width = max(50, int(480 / col_count))
        col_widths = [col_width] * col_count
        story.append(
            KeepTogether(
                [
                    _key_value_table(matrix, font_size=9, col_widths=col_widths),
                    Spacer(1, 4),
                    Paragraph("评分依据", styles["label"]),
                    _safe_paragraph(scores.get("rationale", "暂无"), styles["score_note"]),
                ]
            )
        )
    else:
        story.append(_safe_paragraph("暂无", styles["score_note"]))
    story.append(Spacer(1, 8))

    bg, br = _palette("risk")
    risk_title = _section_title("主要风险", colors.HexColor("#b45309"))
    top_risks = report.get("top_risks", [])
    if isinstance(top_risks, list) and top_risks:
        items = [
            f"{risk.get('risk', '风险')}（{_label(risk.get('priority', '暂无'))}）— {risk.get('impact', '暂无')}"
            for risk in top_risks
            if isinstance(risk, dict)
        ]
        items = _dedupe(items)
        risk_card = _card_block(None, [_list_to_paragraph(items, styles["body"])], styles, background=bg, border=br)
        story.append(KeepTogether([risk_title, risk_card]))
    else:
        risk_card = _card_block(None, [_safe_paragraph("暂无", styles["body"])], styles, background=bg, border=br)
        story.append(KeepTogether([risk_title, risk_card]))
    story.append(Spacer(1, 8))

    bg, br = _palette("recommendation")
    rec_title = _section_title("改进建议", colors.HexColor("#2f6f3e"))
    recs = report.get("recommendations", {})
    actions = recs.get("actions") if isinstance(recs, dict) else []
    if isinstance(actions, list) and actions:
        items = []
        for action in actions:
            if not isinstance(action, dict):
                continue
            items.append(
                f"{action.get('action', '措施')} — {_label(action.get('priority', '暂无'))} / "
                f"{_label(action.get('difficulty', '暂无'))} / 预算：{_label(action.get('budget', '暂无'))}"
            )
        items = _dedupe(items)
        rec_card = _card_block(None, [_list_to_paragraph(items, styles["body"])], styles, background=bg, border=br)
        story.append(KeepTogether([rec_title, rec_card]))
    else:
        rec_card = _card_block(None, [_safe_paragraph("暂无", styles["body"])], styles, background=bg, border=br)
        story.append(KeepTogether([rec_title, rec_card]))
    story.append(Spacer(1, 8))

    regions_title = _section_title("区域分析", colors.HexColor("#a16207"))
    regions = report.get("regions", [])
    if isinstance(regions, list) and regions:
        first_region = True
        for idx, region in enumerate(regions, start=1):
            if not isinstance(region, dict):
                continue
            region_names = region.get("regionName") or []
            if isinstance(region_names, list):
                name = "、".join([str(item) for item in region_names if str(item).strip()]) or f"区域 {idx}"
            else:
                name = str(region_names) if region_names else f"区域 {idx}"
            card_body = [
                Paragraph("潜在安全隐患", styles["label"]),
                _list_to_paragraph(region.get("potentialHazards", []), styles["body"]),
                Paragraph("特殊人群相关隐患", styles["label"]),
                _list_to_paragraph(region.get("specialHazards", []), styles["body"]),
                Paragraph("色彩与照明评估", styles["label"]),
                _list_to_paragraph(region.get("colorAndLightingEvaluation", []), styles["body"]),
                Paragraph("改进建议", styles["label"]),
                _list_to_paragraph(region.get("suggestions", []), styles["body"]),
            ]
            bg, br = _palette("region")
            card_block = _card_block(name, card_body, styles, background=bg, border=br)
            if first_region:
                story.append(KeepTogether([regions_title, card_block, Spacer(1, 6)]))
                first_region = False
            else:
                story.append(KeepTogether([card_block, Spacer(1, 6)]))
    else:
        story.append(KeepTogether([regions_title, _safe_paragraph("暂无", styles["body"])]))

    comfort_title = _section_title("舒适与健康", colors.HexColor("#1d4ed8"))
    comfort = report.get("comfort", {})
    bg, br = _palette("comfort")
    story.append(
        KeepTogether(
            [
                comfort_title,
                _card_block(
                    None,
                    [
                        Paragraph("观察结果", styles["label"]),
                        _list_to_paragraph(
                            comfort.get("observations", []) if isinstance(comfort, dict) else [], styles["body"]
                        ),
                        Paragraph("建议", styles["label"]),
                        _list_to_paragraph(
                            comfort.get("suggestions", []) if isinstance(comfort, dict) else [], styles["body"]
                        ),
                    ],
                    styles,
                    background=bg,
                    border=br,
                ),
            ]
        )
    )
    story.append(Spacer(1, 8))

    compliance_title = _section_title("安全规范参考", colors.HexColor("#6d28d9"))
    compliance = report.get("compliance", {})
    checklist = (compliance.get("checklist") or []) if isinstance(compliance, dict) else []
    checklist_items = [
        f"{item.get('item', '检查项')}（{_label(item.get('priority', '暂无'))}）"
        for item in checklist
        if isinstance(item, dict)
    ]
    bg, br = _palette("compliance")
    story.append(
        KeepTogether(
            [
                compliance_title,
                _card_block(
                    None,
                    [
                        Paragraph("说明", styles["label"]),
                        _list_to_paragraph(
                            compliance.get("notes", []) if isinstance(compliance, dict) else [], styles["body"]
                        ),
                        Paragraph("检查清单", styles["label"]),
                        _list_to_paragraph(checklist_items, styles["body"]),
                    ],
                    styles,
                    background=bg,
                    border=br,
                ),
            ]
        )
    )
    story.append(Spacer(1, 8))

    action_title = _section_title("行动计划", colors.HexColor("#2f6f3e"))
    action_plan = report.get("action_plan", [])
    action_items = [
        f"{item.get('action', '措施')}（{_label(item.get('priority', '暂无'))}）— {item.get('timeline', '暂无')}"
        for item in action_plan
        if isinstance(item, dict)
    ]
    bg, br = _palette("action")
    story.append(
        KeepTogether(
            [
                action_title,
                _card_block(
                    None,
                    [_list_to_paragraph(action_items, styles["body"])],
                    styles,
                    background=bg,
                    border=br,
                ),
            ]
        )
    )

    limitations_title = _section_title("分析局限", colors.HexColor("#92400e"))
    bg, br = _palette("limitations")
    story.append(
        KeepTogether(
            [
                limitations_title,
                _card_block(
                    None,
                    [_list_to_paragraph(report.get("limitations", []), styles["body"])],
                    styles,
                    background=bg,
                    border=br,
                ),
            ]
        )
    )

    doc.build(story)
