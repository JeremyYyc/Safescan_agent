import { useEffect, useMemo, useRef } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import { useOutletContext } from "react-router-dom";

function ThreadContent() {
  const {
    activeChatId,
    activeChatType,
    draftMode,
    regionVisible,
    regionStream,
    reportData,
    images,
    toUploadUrl,
    handleRunAnalysis,
    isRunning,
    reportLocked,
    videoFile,
    setVideoFile,
    selectedVideoPath,
    fileInputRef,
    attributes,
    toggleAttribute,
    videoStatus,
    chatHistory,
    isLoadingMessages,
    chatEndRef,
    apiBase,
    pdfExportByChat,
    generatePdfForChat,
    handleDownloadPdf,
    handlePreviewPdf,
    chatReportRefs,
    reportChats,
    pendingReportIds,
    handleRunCompareSelection,
    handleRemovePendingReportSelection,
    handleRemoveReportRef,
    setPreviewImage,
    setReportPickerOpen,
  } = useOutletContext();

  const selectedVideoName = selectedVideoPath
    ? String(selectedVideoPath).split(/[/\\\\]/).pop()
    : "";
  const showMainPanels = Boolean(activeChatId || draftMode);
  const resolvedChatType = activeChatType || "report";
  const isBotChat = resolvedChatType === "bot";
  const hasChatbotReportRefs = Array.isArray(chatReportRefs) && chatReportRefs.length > 0;
  const hasPendingSelections = Array.isArray(pendingReportIds) && pendingReportIds.length > 0;
  const attachedSourceIds = useMemo(
    () =>
      new Set(
        (chatReportRefs || [])
          .filter((ref) => ref && ref.status !== "deleted" && ref.source_chat_id)
          .map((ref) => Number(ref.source_chat_id))
          .filter((id) => !Number.isNaN(id))
      ),
    [chatReportRefs]
  );
  const pendingItems = useMemo(() => {
    const reportMap = new Map((reportChats || []).map((chat) => [Number(chat.id), chat]));
    return [...new Set(pendingReportIds || [])]
      .filter((sourceChatId) => !attachedSourceIds.has(sourceChatId))
      .map((sourceChatId) => {
        const chat = reportMap.get(Number(sourceChatId));
        return {
          source_chat_id: sourceChatId,
          title: chat?.title || `Chat ${sourceChatId}`,
          is_pending: true,
        };
      });
  }, [pendingReportIds, reportChats, attachedSourceIds]);
  const showReportPanels = !isBotChat && showMainPanels;
  const hasReportData =
    reportData && typeof reportData === "object" && Object.keys(reportData).length > 0;
  const reportAutoScrollRef = useRef(false);
  const pdfExport = activeChatId ? pdfExportByChat?.[activeChatId] : null;
  const pdfStatus = pdfExport?.status || "idle";
  const pdfUrl = pdfExport?.url || "";
  const resolvedPdfUrl = pdfUrl ? toUploadUrl(pdfUrl) : "";
  const pdfReportId = pdfExport?.reportId ?? null;
  const pdfError = pdfExport?.error || "";

  const renderMarkdown = useMemo(() => {
    marked.setOptions({ breaks: true });
    return (text) => {
      const raw = marked.parse(String(text || "").trim());
      return { __html: DOMPurify.sanitize(raw) };
    };
  }, []);

  function renderList(items, emptyLabel = "N/A") {
    if (!Array.isArray(items) || items.length === 0) {
      return <div className="region-text">{emptyLabel}</div>;
    }
    return (
      <ul className="region-list">
        {items.map((item, idx) => (
          <li key={`${String(item)}-${idx}`}>{String(item)}</li>
        ))}
      </ul>
    );
  }

  function renderKeyValues(obj) {
    if (!obj || typeof obj !== "object") {
      return <div className="region-text">N/A</div>;
    }
    return (
      <div className="region-fields">
        {Object.entries(obj).map(([key, value]) => (
          <div className="region-field" key={key}>
            <div className="region-label">{key}</div>
            {Array.isArray(value) ? renderList(value) : (
              <pre className="region-text">{String(value ?? "N/A")}</pre>
            )}
          </div>
        ))}
      </div>
    );
  }

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) {
      return undefined;
    }
    if (!window.matchMedia("(max-width: 720px)").matches) {
      return undefined;
    }
    if (!regionVisible) {
      reportAutoScrollRef.current = false;
      return undefined;
    }
    if (reportAutoScrollRef.current) {
      return undefined;
    }
    const behavior = "smooth";
    reportAutoScrollRef.current = true;
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        window.scrollTo({
          top: document.documentElement.scrollHeight,
          behavior,
        });
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [regionVisible]);

  return (
    <>
      {showMainPanels && (
        <>
          {showReportPanels && (
            <>
              <section className="panel analysis-panel">
                <header className="panel-header">
                  <h2>Video Analysis</h2>
                  <span className="panel-tag">Workflow</span>
                </header>

                <div className="panel-section">
                  <label className="label">Upload video file</label>
                  <div className="file-picker">
                    <button
                      className="btn ghost file-picker-btn"
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={reportLocked || isRunning}
                    >
                      Choose video
                    </button>
                    <span className="file-picker-name">
                      {videoFile
                        ? videoFile.name
                        : selectedVideoName
                          ? `Selected: ${selectedVideoName}`
                          : "No file chosen"}
                    </span>
                  </div>
                  <input
                    className="file-input file-input-hidden"
                    type="file"
                    accept="video/*"
                    ref={fileInputRef}
                    disabled={reportLocked || isRunning}
                    onChange={(event) => setVideoFile(event.target.files?.[0] || null)}
                  />
                </div>

                <div className="panel-section">
                  <label className="label">User attributes</label>
                  <div className="chip-grid">
                    <button
                      className={`chip ${attributes.isPregnant ? "active" : ""}`}
                      type="button"
                      onClick={() => toggleAttribute("isPregnant")}
                    >
                      Pregnant
                    </button>
                    <button
                      className={`chip ${attributes.isChildren ? "active" : ""}`}
                      type="button"
                      onClick={() => toggleAttribute("isChildren")}
                    >
                      Children
                    </button>
                    <button
                      className={`chip ${attributes.isElderly ? "active" : ""}`}
                      type="button"
                      onClick={() => toggleAttribute("isElderly")}
                    >
                      Elderly
                    </button>
                    <button
                      className={`chip ${attributes.isDisabled ? "active" : ""}`}
                      type="button"
                      onClick={() => toggleAttribute("isDisabled")}
                    >
                      Disabled
                    </button>
                    <button
                      className={`chip ${attributes.isAllergic ? "active" : ""}`}
                      type="button"
                      onClick={() => toggleAttribute("isAllergic")}
                    >
                      Allergic
                    </button>
                    <button
                      className={`chip ${attributes.isPets ? "active" : ""}`}
                      type="button"
                      onClick={() => toggleAttribute("isPets")}
                    >
                      Pets
                    </button>
                  </div>
                </div>

                <button
                  className="btn solid full"
                  type="button"
                  disabled={reportLocked || isRunning}
                  onClick={handleRunAnalysis}
                >
                  {isRunning ? videoStatus : "Run Analysis"}
                </button>

                <div className="panel-section">
                  <label className="label">Representative images</label>
                  <div className="image-grid">
                    {images.map((path, idx) => {
                      const src = toUploadUrl(path);
                      return (
                        <button
                          className="image-preview-btn"
                          type="button"
                          key={`${path}-${idx}`}
                          onClick={() => setPreviewImage(src)}
                          aria-label="Preview image"
                        >
                          <img src={src} alt="Representative" />
                        </button>
                      );
                    })}
                  </div>
                </div>
              </section>

              {regionVisible && (
                <section className="panel report-panel">
                  <header className="panel-header">
                    <h2>Report</h2>
                    <span className="panel-tag">Generated</span>
                  </header>
                  <div className="region-stream">
                    {regionStream.map((region, idx) => (
                      <div className="region-card" key={`${region.title}-${idx}`}>
                        <div className="region-title-row">
                          <div className="region-title">{region.title}</div>
                          {Array.isArray(region.images) && region.images.length > 0 ? (
                            <div className="region-image-strip">
                              {region.images.map((path, imgIdx) => {
                                const src = toUploadUrl(path);
                                return (
                                  <button
                                    className="region-image-thumb"
                                    type="button"
                                    key={`${path}-${imgIdx}`}
                                    onClick={() => setPreviewImage(src)}
                                    aria-label="Preview region image"
                                  >
                                    <img src={src} alt="Region" />
                                  </button>
                                );
                              })}
                            </div>
                          ) : null}
                        </div>
                        {region.fields.map((field, fieldIndex) => (
                          <div className="region-field" key={`${field.label}-${fieldIndex}`}>
                            <div className="region-label">{field.label}</div>
                            {field.isList ? (
                              <ul className="region-list">
                                {(field.value || []).map((item, itemIndex) => (
                                  <li key={`${field.label}-${itemIndex}`}>{String(item)}</li>
                                ))}
                              </ul>
                            ) : (
                              <pre className="region-text">{String(field.value ?? "N/A")}</pre>
                            )}
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                  {hasReportData && (
                    <div className="region-stream">
                      <div className="region-card">
                        <div className="region-title">Scores</div>
                        <div className="region-field">
                          <div className="region-label">overall</div>
                          <pre className="region-text">
                            {String(reportData.scores?.overall ?? "N/A")}
                          </pre>
                        </div>
                        <div className="region-field">
                          <div className="region-label">dimensions</div>
                          {renderKeyValues(reportData.scores?.dimensions)}
                        </div>
                        <div className="region-field">
                          <div className="region-label">rationale</div>
                          <pre className="region-text">
                            {String(reportData.scores?.rationale ?? "N/A")}
                          </pre>
                        </div>
                      </div>

                      <div className="region-card">
                        <div className="region-title">Top Risks</div>
                        {Array.isArray(reportData.top_risks) && reportData.top_risks.length > 0 ? (
                          <ul className="region-list">
                            {reportData.top_risks.map((risk, idx) => (
                              <li key={`risk-${idx}`}>
                                {risk?.risk || "Risk"} - {risk?.priority || "N/A"} -{" "}
                                {risk?.impact || "N/A"}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <div className="region-text">N/A</div>
                        )}
                      </div>

                      <div className="region-card">
                        <div className="region-title">Recommendations</div>
                        {Array.isArray(reportData.recommendations?.actions) ? (
                          <ul className="region-list">
                            {reportData.recommendations.actions.map((action, idx) => (
                              <li key={`action-${idx}`}>
                                {action?.action || "Action"} - {action?.budget || "N/A"} -{" "}
                                {action?.difficulty || "N/A"} - {action?.priority || "N/A"}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <div className="region-text">N/A</div>
                        )}
                      </div>

                      <div className="region-card">
                        <div className="region-title">Comfort</div>
                        <div className="region-field">
                          <div className="region-label">observations</div>
                          {renderList(reportData.comfort?.observations)}
                        </div>
                        <div className="region-field">
                          <div className="region-label">suggestions</div>
                          {renderList(reportData.comfort?.suggestions)}
                        </div>
                      </div>

                      <div className="region-card">
                        <div className="region-title">Compliance</div>
                        <div className="region-field">
                          <div className="region-label">notes</div>
                          {renderList(reportData.compliance?.notes)}
                        </div>
                        <div className="region-field">
                          <div className="region-label">checklist</div>
                          {Array.isArray(reportData.compliance?.checklist) ? (
                            <ul className="region-list">
                              {reportData.compliance.checklist.map((item, idx) => (
                                <li key={`check-${idx}`}>
                                  {item?.item || "Item"} - {item?.priority || "N/A"}
                                </li>
                              ))}
                            </ul>
                          ) : (
                            <div className="region-text">N/A</div>
                          )}
                        </div>
                      </div>

                      <div className="region-card">
                        <div className="region-title">Action Plan</div>
                        {Array.isArray(reportData.action_plan) ? (
                          <ul className="region-list">
                            {reportData.action_plan.map((item, idx) => (
                              <li key={`plan-${idx}`}>
                                {item?.action || "Action"} - {item?.priority || "N/A"} -{" "}
                                {item?.timeline || "N/A"}
                              </li>
                            ))}
                          </ul>
                        ) : (
                          <div className="region-text">N/A</div>
                        )}
                      </div>

                      <div className="region-card">
                        <div className="region-title">Limitations</div>
                        {renderList(reportData.limitations)}
                      </div>
                    </div>
                  )}
                  {hasReportData && activeChatId && (
                    <div className="pdf-export">
                      <div className="pdf-export-header">
                        <div className="pdf-export-title">PDF Report</div>
                        <div className="pdf-export-subtitle">Export a shareable PDF version.</div>
                      </div>
                      <div className="pdf-export-body">
                        <div className="pdf-export-actions">
                          <button
                            className="btn solid"
                            type="button"
                            onClick={() => handlePreviewPdf(activeChatId, pdfReportId)}
                          >
                            Preview
                          </button>
                          <button
                            className="btn ghost"
                            type="button"
                            onClick={() => handleDownloadPdf(activeChatId, pdfReportId)}
                          >
                            Download
                          </button>
                        </div>
                        {pdfStatus === "generating" && (
                          <div className="pdf-export-text">Generating PDF...</div>
                        )}
                        {pdfStatus === "error" && (
                          <div className="pdf-export-error">{pdfError || "PDF generation failed."}</div>
                        )}
                      </div>
                    </div>
                  )}
                </section>
              )}
            </>
          )}
          {isBotChat && activeChatId && (hasChatbotReportRefs || hasPendingSelections) && (
            <section className="panel analysis-panel">
              <header className="panel-header">
                <h2>Chatbot Reports</h2>
                <span className="panel-tag">Compare</span>
              </header>
              <div className="panel-section">
                <button
                  className="btn solid"
                  type="button"
                  disabled={!hasPendingSelections}
                  onClick={() => handleRunCompareSelection(activeChatId)}
                >
                  Run Analysis
                </button>
              </div>
              <div className="panel-section">
                <label className="label">Attach report</label>
                <div className="file-picker">
                  <button
                    className="btn ghost file-picker-btn"
                    type="button"
                    onClick={() => setReportPickerOpen(true)}
                  >
                    Select reports
                  </button>
                </div>
              </div>
              <div className="panel-section">
                <label className="label">Attached reports</label>
                <ul className="region-list">
                  {chatReportRefs.map((ref) => {
                    const title = ref.source_title || "Deleted report chat";
                    const isDeleted = ref.status === "deleted";
                    return (
                      <li key={`${ref.report_id}-${ref.source_chat_id || "unknown"}`}>
                        {title}
                        {isDeleted ? " (deleted)" : ""}
                        {!isDeleted ? (
                          <button
                            className="btn ghost"
                            type="button"
                            onClick={() =>
                              handleRemoveReportRef(
                                ref.report_id,
                                ref.source_type === "pdf" ? { deleteSource: true } : {}
                              )
                            }
                          >
                            Remove
                          </button>
                        ) : null}
                      </li>
                    );
                  })}
                  {pendingItems.map((item) => (
                    <li key={`pending-${item.source_chat_id}`}>
                      {item.title} (pending)
                      <button
                        className="btn ghost"
                        type="button"
                        onClick={() => handleRemovePendingReportSelection(item.source_chat_id)}
                      >
                        Remove
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          )}
          {chatHistory.length > 0 && (
            <section className="chat-stream">
              <div className="chat-thread">
                {chatHistory.map((item) => (
                  <div className={`chat-item ${item.role}`} key={item.id || `${item.role}-${item.content}`}>
                    {item.role === "assistant" ? (
                      <div
                        className={`chat-message ${item.role}`}
                        dangerouslySetInnerHTML={renderMarkdown(item.content)}
                      />
                    ) : (
                      <div className={`chat-message ${item.role}`}>{item.content}</div>
                    )}
                  </div>
                ))}
                <div ref={chatEndRef} className="chat-end" />
              </div>
            </section>
          )}
          {isLoadingMessages && chatHistory.length === 0 && (
            <section className="chat-stream">
              <div className="chat-empty">Loading chat...</div>
            </section>
          )}
        </>
      )}
    </>
  );
}

export default ThreadContent;
