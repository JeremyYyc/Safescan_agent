"""Safe report failure messages; never expose provider bodies or credentials."""


class ReportGenerationError(RuntimeError):
    pass


def model_request_failure(error, tier):
    status = getattr(error, 'status_code', None)
    error_type = type(error).__name__
    body = getattr(error, 'body', None)
    details = body.get('error', body) if isinstance(body, dict) else {}
    code = details.get('code') if isinstance(details, dict) else None
    suffix = f' (HTTP {status})' if isinstance(status, int) else ''
    if error_type == 'APITimeoutError':
        return ReportGenerationError(
            f'模型 {tier} 响应超时。已完成可用重试或降级，本次未保存报告。'
        )
    if error_type == 'APIConnectionError':
        return ReportGenerationError(
            f'模型 {tier} 连接失败。已完成可用重试或降级，本次未保存报告。'
        )
    if code == 'Arrearage':
        reason = '模型服务账户余额或计费状态异常（Arrearage），请检查阿里云账户余额和服务状态。'
    else:
        reason = f'请检查 ALIBABA_MODEL_{tier}、API 权限和服务地址。'
    return ReportGenerationError(f'模型 {tier} 请求失败{suffix}。{reason}本次未保存报告。')


def has_report_content(report):
    return (isinstance(report, dict) and 'error' not in report
            and isinstance(report.get('regions'), list) and bool(report['regions']))


def require_report_content(report):
    if not has_report_content(report):
        raise ReportGenerationError('模型重试后仍未生成有效报告，本次未保存报告，请重新分析。')
