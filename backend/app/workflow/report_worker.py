from app.workflow.report_queue import ReportJobWorker

if __name__ == '__main__':
    ReportJobWorker().serve_forever()
