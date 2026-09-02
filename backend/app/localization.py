"""Locale policy shared by model prompts and server-rendered content."""

from app.settings import get_settings


LOCALE_PROFILES = {
    "zh-CN": (
        "面向中国大陆用户，采用自然的中国大陆用语；使用公制单位、摄氏度和人民币。"
        "涉及紧急求助时使用中国大陆常用号码并提醒以当地官方信息为准；"
        "涉及法规、标准、医疗或法律判断时提示核实最新国家和地方规定。"
    ),
    "en-US": "Use clear US English and locally familiar units and conventions.",
}

ZH_CN_API_MESSAGES = {
    "Unauthorized": "登录状态已失效，请重新登录",
    "Invalid email or password": "邮箱或密码错误",
    "Email already exists": "该邮箱已注册",
    "Failed to create user": "创建用户失败",
    "Username is required": "请输入用户名",
    "Failed to update profile": "个人资料更新失败",
    "Failed to load profile": "个人资料加载失败",
    "Chat not found": "未找到该对话",
    "Source chat not found": "未找到来源对话",
    "Report not found": "未找到该报告",
    "Report data not found": "未找到报告数据",
    "Report reference not found": "未找到关联报告",
    "No report found for source chat": "来源对话中没有可用报告",
    "Failed to create chat": "创建对话失败",
    "Failed to update chat": "更新对话失败",
    "Failed to delete chat": "删除对话失败",
    "Failed to add report reference": "添加关联报告失败",
    "Database is not configured": "数据库尚未正确配置",
    "No fields to update": "没有需要更新的内容",
    "title must be a non-empty string": "标题不能为空",
    "Question is required": "请输入问题",
    "chat_id is required": "缺少对话编号",
    "video_asset_id is required": "缺少视频资源编号",
    "Asset is not a video": "所选文件不是视频",
    "Video asset not found": "未找到视频资源",
    "Asset not found": "未找到该资源",
    "Empty upload": "上传文件为空",
    "Upload exceeds configured memory/size limit": "上传文件超过大小限制",
    "Upload capacity reached; retry after this upload finishes": "当前上传任务已满，请等待现有上传完成后重试",
    "Expected a JSON chat request": "问答请求格式不正确",
    "Expected a JSON object": "请求内容必须为 JSON 对象",
    "Invalid user_input format": "用户输入格式不正确",
    "Report is not a PDF": "该报告不是 PDF 文件",
    "PDF source missing": "PDF 源文件缺失",
    "PDF file not found": "未找到 PDF 文件",
}


def llm_language_directive() -> str:
    settings = get_settings()
    locale = settings.DEFAULT_LOCALE.strip() or "zh-CN"
    language = settings.LLM_OUTPUT_LANGUAGE.strip() or "Simplified Chinese"
    profile = LOCALE_PROFILES.get(locale, f"Follow the locale conventions for {locale}.")
    return (
        f"强制输出语言：所有面向用户的自然语言内容必须使用 {language}。"
        "固定 JSON 键名、工具名和协议枚举值保持原样，不要翻译。"
        f"地区体验要求：{profile}"
    )


def localize_api_message(message):
    if not isinstance(message, str):
        return message
    if get_settings().DEFAULT_LOCALE == "zh-CN":
        return ZH_CN_API_MESSAGES.get(message, message)
    return message
