export function hasReportContent(report) {
  return Boolean(
    report && typeof report === "object" &&
    !Object.hasOwn(report, "error") &&
    Array.isArray(report.regions) && report.regions.length > 0
  );
}

export function hasReportHistoryContent(report) {
  return report?.source_type === "pdf" || hasReportContent(report);
}
