"""Safe report failure messages; never expose provider bodies or credentials."""


class ReportGenerationError(RuntimeError):
    pass


def model_request_failure(error, tier):
    status = getattr(error, 'status_code', None)
    body = getattr(error, 'body', None)
    details = body.get('error', body) if isinstance(body, dict) else {}
    code = details.get('code') if isinstance(details, dict) else None
    suffix = f' (HTTP {status})' if isinstance(status, int) else ''
    if code == 'Arrearage':
        reason = 'Provider billing restriction (Arrearage). Check the Alibaba Cloud account balance and service billing status.'
    else:
        reason = f'Check ALIBABA_MODEL_{tier}, API permissions and the endpoint.'
    return ReportGenerationError(f'Model {tier} request failed{suffix}. {reason} No report was saved.')


def has_report_content(report):
    return (isinstance(report, dict) and 'error' not in report
            and isinstance(report.get('regions'), list) and bool(report['regions']))


def require_report_content(report):
    if not has_report_content(report):
        raise ReportGenerationError('The model did not produce report content after retries. No report was saved; please retry.')
