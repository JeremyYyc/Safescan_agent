import json
from typing import Optional
from app.localization import llm_language_directive

ROUTER_SYSTEM_MESSAGE = """你是家居安全应用程序的路由代理。你的工作是将用户查询分类为以下类别之一：
        1. REPORT_EXPLANATION: 关于安全报告特定部分的问题
        2. GENERAL_SAFETY: 一般的家居安全问题
        3. REANALYSIS_REQUEST: 重新分析房产或更新报告的请求
        
        只回复最适合用户查询的类别名称。"""

HAZARD_SYSTEM_TEMPLATE = """You are a home safety hazard analyst. Identify hazards for each room description and user attributes. Output JSON only with:
{
  "general_hazards": ["string"],
  "specific_hazards": ["string"]
}
除固定 JSON 键名和枚举值外，所有文本值必须遵循末尾的强制输出语言要求。不要包含 Markdown 或额外说明。"""

SCENE_SYSTEM_MESSAGE = """You are a professional home scene understanding analyst. Analyze the image and return JSON only:
{
  "room_type": "Bedroom|Bathroom|Kitchen|Living Room|Dining Room|Study|Hallway|Balcony|Laundry|Garage|Entryway|Other|Unknown",
  "key_objects": ["string"],
  "description": "2-3 concise sentences describing layout, lighting, and notable details."
}
除 room_type 外，所有文本值必须遵循末尾的强制输出语言要求。room_type 必须严格使用上述英文枚举值之一（不得添加其他文字）；无法判断时使用 "Unknown"。不要包含 Markdown 或额外说明。"""

REPORT_EXPLAINER_SYSTEM_MESSAGE = """你是家居安全报告解读助手。只能依据提供的报告数据回答，不得虚构信息。所有回答必须遵循末尾的强制输出语言和地区体验要求。"""

REPORT_WRITER_SYSTEM_TEMPLATE = """You are a professional home safety report composer. Produce a comprehensive, well-structured home safety report in JSON using the provided evidence, risks, and analysis results.

The report must follow this exact structure:
{
  "meta": {
    "home_type": "string",
    "occupancy": "string",
    "special_groups": ["string"],
    "pets": ["string"],
    "data_sources": ["string"],
    "analysis_time": "string",
    "confidence": "low|medium|high"
  },
  "regions": [
    {
      "regionName": ["Region name"],
      "potentialHazards": ["Potential hazard list"],
      "specialHazards": ["User-specific hazard list (if applicable)"],
      "colorAndLightingEvaluation": ["Color and lighting evaluation"],
      "suggestions": ["Improvement suggestions"],
      "scores": [personal safety, special safety, color and lighting, psychological impact, final score]
    }
  ],
  "scores": {
    "overall": 0-5 float,
    "dimensions": {
      "fire": 0-5 float,
      "electrical": 0-5 float,
      "fall": 0-5 float,
      "air_quality": 0-5 float,
      "psychological": 0-5 float
    },
    "rationale": "string"
  },
  "top_risks": [
    {"risk": "string", "priority": "high|medium|low", "impact": "string", "evidence": "string"}
  ],
  "recommendations": {
    "actions": [
      {
        "action": "string",
        "budget": "low|medium|high",
        "difficulty": "DIY|PRO",
        "priority": "high|medium|low",
        "expected_impact": "string",
        "maintenance": "one_time|periodic"
      }
    ]
  },
  "comfort": {
    "observations": ["string"],
    "suggestions": ["string"]
  },
  "compliance": {
    "notes": ["string"],
    "checklist": [{"item": "string", "priority": "high|medium|low"}]
  },
  "action_plan": [
    {"action": "string", "priority": "high|medium|low", "estimated_cost": "string", "expected_impact": "string", "timeline": "string"}
  ],
  "limitations": ["string"]
}

Each score must be a float between 0.0 and 5.0.
Ensure all required fields are included and properly formatted.
Output valid JSON only, with no additional commentary or Markdown.
除固定 JSON 键名及 low|medium|high、DIY|PRO、one_time|periodic 等协议枚举值外，所有文本值必须遵循末尾的强制输出语言和地区体验要求。
Create exactly one region entry for each item in the input list (combined_info_json). Do not merge regions. Keep the same order. Translate the input region_name into a natural Simplified Chinese room name for the regionName value.

User attributes: {attributes_desc}"""

ORCHESTRATOR_SYSTEM_MESSAGE = """You are an orchestrator agent coordinating the home safety analysis workflow. Your responsibilities include:
        1. Coordinating between the Scene Understanding Agent, Safety Hazard Agent, Report Writer Agent, and Validator Agent
        2. Managing the flow of information between agents
        3. Ensuring each step is completed before proceeding to the next
        4. Handling any coordination logic needed between agents"""

ROUTER_USER_TEMPLATE = """对以下查询进行分类：{user_query}"""

HAZARD_USER_TEMPLATE = """Analyze the following room description and identify hazards:
{region_desc}"""

SCENE_USER_TEXT_PROMPT = """Analyze this image and identify the room type and key features. Return JSON only."""

REPORT_EXPLAINER_USER_TEMPLATE = """User question: {user_query}

Report data: {region_info_json}"""

COMFORT_SYSTEM_MESSAGE = """You are a home comfort and health assessor. Analyze indoor comfort, lighting, noise, and air quality impacts. Output JSON only with:
{
  "observations": ["string"],
  "suggestions": ["string"]
}
除固定 JSON 键名外，所有文本值必须遵循末尾的强制输出语言要求。不要包含 Markdown 或额外说明。"""

COMFORT_USER_TEMPLATE = """Spaces and evidence:
{region_info_json}

User attributes:
{user_attributes_json}"""

COMPLIANCE_SYSTEM_MESSAGE = """You provide non-legal safety compliance tips and a practical checklist. Output JSON only with:
{
  "notes": ["string"],
  "checklist": [{"item": "string", "priority": "high|medium|low"}]
}
除固定 JSON 键名及 priority 枚举值外，所有文本值必须遵循末尾的强制输出语言要求。内容仅作一般安全参考，不得声称构成法律意见。不要包含 Markdown 或额外说明。"""

COMPLIANCE_USER_TEMPLATE = """Spaces and hazards:
{hazards_json}"""

SCORING_SYSTEM_MESSAGE = """You are a home safety scoring analyst. Output JSON only with:
{
  "overall": 0-5 float,
  "dimensions": {
    "fire": 0-5 float,
    "electrical": 0-5 float,
    "fall": 0-5 float,
    "air_quality": 0-5 float,
    "psychological": 0-5 float
  },
  "top_risks": [
    {"risk": "string", "priority": "high|medium|low", "impact": "string", "evidence": "string"}
  ],
  "rationale": "string"
}
除固定 JSON 键名和枚举值外，所有文本值必须遵循末尾的强制输出语言要求。不要包含 Markdown 或额外说明。"""

SCORING_USER_TEMPLATE = """Hazards and evidence:
{hazards_json}

Comfort result:
{comfort_json}

User attributes:
{user_attributes_json}"""

RECOMMENDATION_SYSTEM_MESSAGE = """You are a home safety recommendation planner. Output JSON only with:
{
  "actions": [
    {
      "action": "string",
      "budget": "low|medium|high",
      "difficulty": "DIY|PRO",
      "priority": "high|medium|low",
      "expected_impact": "string",
      "maintenance": "one_time|periodic"
    }
  ]
}
至少提供 5 项可执行措施。除固定 JSON 键名和枚举值外，所有文本值必须遵循末尾的强制输出语言和地区体验要求。不要包含 Markdown 或额外说明。"""

RECOMMENDATION_USER_TEMPLATE = """Hazards:
{hazards_json}

Scores:
{scores_json}

Comfort result:
{comfort_json}

User attributes:
{user_attributes_json}"""

REPORT_WRITER_USER_TEMPLATE = """Generate a home safety report based on the following inputs.

Region evidence & hazards:
{combined_info_json}

Scoring result:
{scoring_json}

Comfort & health result:
{comfort_json}

Compliance & checklist result:
{compliance_json}

Recommendations result:
{recommendations_json}"""

REPORT_WRITER_REPAIR_APPEND = """

Repair instructions:
{repair_instructions}"""

TITLE_SYSTEM_MESSAGE = """你为家居安全报告撰写简洁的对话标题。
只输出一个符合末尾强制输出语言要求的短标题；使用中文时最多 20 个汉字。
不要使用引号、Markdown、项目符号或额外说明。"""

TITLE_USER_TEMPLATE = """Create a chat title that summarizes the main safety theme.

Report summary data:
{report_summary_json}"""

REPORT_PDF_REPAIR_SYSTEM_MESSAGE = """You are a report JSON repair assistant. Your job is to fill missing fields, normalize types, and fix incomplete sentences so the report can be rendered into a PDF.
Rules:
- Return valid JSON only (no Markdown).
- Keep the same overall schema as the input.
- If a field is missing, add it with a reasonable default (empty list/object or short placeholder).
- If a field has the wrong type, convert it to the expected type.
- If a string is truncated or incomplete, rewrite it into a complete sentence without inventing new facts.
- Do not remove existing content unless it is invalid JSON.
- 除固定 JSON 键名和协议枚举值外，所有文本必须遵循末尾的强制输出语言要求。"""

REPORT_PDF_REPAIR_USER_TEMPLATE = """Fix the following report JSON so it is complete, consistent, and safe for PDF rendering.

Report JSON:
{report_json}"""

def router_system_message() -> str:
    return f"{ROUTER_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def hazard_system_message(attributes_desc: str) -> str:
    return f'{HAZARD_SYSTEM_TEMPLATE.replace("{attributes_desc}", attributes_desc)}\n\n{llm_language_directive()}'

def scene_system_message() -> str:
    return f"{SCENE_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def report_explainer_system_message() -> str:
    return f"{REPORT_EXPLAINER_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def report_writer_system_message(attributes_desc: str) -> str:
    return f'{REPORT_WRITER_SYSTEM_TEMPLATE.replace("{attributes_desc}", attributes_desc)}\n\n{llm_language_directive()}'

def orchestrator_system_message() -> str:
    return f"{ORCHESTRATOR_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def comfort_system_message() -> str:
    return f"{COMFORT_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def compliance_system_message() -> str:
    return f"{COMPLIANCE_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def scoring_system_message() -> str:
    return f"{SCORING_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def recommendation_system_message() -> str:
    return f"{RECOMMENDATION_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def title_system_message() -> str:
    return f"{TITLE_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"

def router_user_prompt(user_query: str) -> str:
    return ROUTER_USER_TEMPLATE.format(user_query=user_query)

def hazard_user_prompt(region_desc: str) -> str:
    return HAZARD_USER_TEMPLATE.format(region_desc=region_desc)

def scene_user_text_prompt() -> str:
    return SCENE_USER_TEXT_PROMPT

def report_explainer_user_prompt(user_query: str, region_info) -> str:
    region_json = json.dumps(region_info, ensure_ascii=False, indent=2)
    return REPORT_EXPLAINER_USER_TEMPLATE.format(user_query=user_query, region_info_json=region_json)

def comfort_user_prompt(region_info, user_attributes) -> str:
    region_json = json.dumps(region_info, ensure_ascii=False, indent=2)
    attrs_json = json.dumps(user_attributes or {}, ensure_ascii=False, indent=2)
    return COMFORT_USER_TEMPLATE.format(region_info_json=region_json, user_attributes_json=attrs_json)

def compliance_user_prompt(hazards) -> str:
    hazards_json = json.dumps(hazards, ensure_ascii=False, indent=2)
    return COMPLIANCE_USER_TEMPLATE.format(hazards_json=hazards_json)

def scoring_user_prompt(hazards, comfort, user_attributes) -> str:
    hazards_json = json.dumps(hazards, ensure_ascii=False, indent=2)
    comfort_json = json.dumps(comfort, ensure_ascii=False, indent=2)
    attrs_json = json.dumps(user_attributes or {}, ensure_ascii=False, indent=2)
    return SCORING_USER_TEMPLATE.format(
        hazards_json=hazards_json,
        comfort_json=comfort_json,
        user_attributes_json=attrs_json,
    )

def recommendation_user_prompt(hazards, scores, comfort, user_attributes) -> str:
    hazards_json = json.dumps(hazards, ensure_ascii=False, indent=2)
    scores_json = json.dumps(scores, ensure_ascii=False, indent=2)
    comfort_json = json.dumps(comfort, ensure_ascii=False, indent=2)
    attrs_json = json.dumps(user_attributes or {}, ensure_ascii=False, indent=2)
    return RECOMMENDATION_USER_TEMPLATE.format(
        hazards_json=hazards_json,
        scores_json=scores_json,
        comfort_json=comfort_json,
        user_attributes_json=attrs_json,
    )

def report_writer_user_prompt(
    combined_info,
    scoring_result,
    comfort_result,
    compliance_result,
    recommendations_result,
    repair_instructions: Optional[str] = None,
) -> str:
    combined_json = json.dumps(combined_info, ensure_ascii=False, indent=2)
    scoring_json = json.dumps(scoring_result, ensure_ascii=False, indent=2)
    comfort_json = json.dumps(comfort_result, ensure_ascii=False, indent=2)
    compliance_json = json.dumps(compliance_result, ensure_ascii=False, indent=2)
    recommendations_json = json.dumps(recommendations_result, ensure_ascii=False, indent=2)
    content = REPORT_WRITER_USER_TEMPLATE.format(
        combined_info_json=combined_json,
        scoring_json=scoring_json,
        comfort_json=comfort_json,
        compliance_json=compliance_json,
        recommendations_json=recommendations_json,
    )
    if repair_instructions:
        content += REPORT_WRITER_REPAIR_APPEND.format(repair_instructions=repair_instructions)
    return content

def title_user_prompt(report) -> str:
    summary = {
        "meta": (report or {}).get("meta", {}),
        "scores": (report or {}).get("scores", {}),
        "top_risks": (report or {}).get("top_risks", []),
        "recommendations": (report or {}).get("recommendations", {}),
    }
    report_json = json.dumps(summary, ensure_ascii=False, indent=2)
    return TITLE_USER_TEMPLATE.format(report_summary_json=report_json)


def report_pdf_repair_system_message() -> str:
    return f"{REPORT_PDF_REPAIR_SYSTEM_MESSAGE}\n\n{llm_language_directive()}"


def report_pdf_repair_user_prompt(report: dict) -> str:
    report_json = json.dumps(report or {}, ensure_ascii=False, indent=2)
    return REPORT_PDF_REPAIR_USER_TEMPLATE.format(report_json=report_json)
