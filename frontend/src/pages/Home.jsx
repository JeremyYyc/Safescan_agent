import { useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import { marked } from "marked";
import "../styles/home.css";

function HomePage({
  sidebarOpen,
  setSidebarOpen,
  handleLogout,
  handleOpenGuide,
  guideOpen,
  guideLoading,
  guideSections,
  guideError,
  handleCloseGuide,
  handleNewChat,
  handleSelectChat,
  handleRenameChat,
  handleDeleteChat,
  handleTogglePin,
  handleProfile,
  authUser,
  chats,
  activeChatId,
  isLoadingChats,
  isLoadingMessages,
  chatHistory,
  chatEndRef,
  questionInput,
  setQuestionInput,
  handleChat,
  isChatting,
  chatPhase,
  chatSendDisabled,
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
  formatChatTitle,
}) {
  const displayName = authUser?.username || authUser?.email || "User";
  const displayEmail = authUser?.email || "";
  const avatarLetter = displayName ? String(displayName).trim().charAt(0).toUpperCase() : "U";
  const [openMenuId, setOpenMenuId] = useState(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const [previewImage, setPreviewImage] = useState("");
  const [openGuideId, setOpenGuideId] = useState("");
  const chatInputRef = useRef(null);
  const selectedVideoName = selectedVideoPath
    ? String(selectedVideoPath).split(/[/\\\\]/).pop()
    : "";
  const showMainPanels = Boolean(activeChatId);
  const hasReportData =
    reportData && typeof reportData === "object" && Object.keys(reportData).length > 0;

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
    function handleClose(event) {
      const target = event.target;
      if (
        target.closest(".chat-menu") ||
        target.closest(".sidebar-history-menu")
      ) {
        return;
      }
      setOpenMenuId(null);
    }

    function handleKey(event) {
      if (event.key === "Escape") {
        setOpenMenuId(null);
      }
    }

    document.addEventListener("click", handleClose);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("click", handleClose);
      document.removeEventListener("keydown", handleKey);
    };
  }, []);

  useEffect(() => {
    if (!previewImage) {
      return undefined;
    }
    function handleKey(event) {
      if (event.key === "Escape") {
        setPreviewImage("");
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [previewImage]);

  useEffect(() => {
    const node = chatInputRef.current;
    if (!node) {
      return;
    }
    node.style.height = "auto";
    const maxHeight = 160;
    const next = Math.min(node.scrollHeight, maxHeight);
    node.style.height = `${next}px`;
    node.style.overflowY = node.scrollHeight > maxHeight ? "auto" : "hidden";
  }, [questionInput]);

  return (
    <div className={`page ${sidebarOpen ? "sidebar-open" : "sidebar-collapsed"}`}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-icon">
            <img src="/smart-home.png" alt="Home Safety" />
          </div>
          <div>
            <div className="brand-title">Safe-Scan Home Safety Agent</div>
            <div className="brand-subtitle">Visual risk audit for your space</div>
          </div>
        </div>
        <div className="top-actions">
          <button className="btn ghost" type="button" onClick={handleOpenGuide}>
            Quick Guide
          </button>
          <button className="btn ghost" type="button" onClick={handleLogout}>
            Log out
          </button>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <div className="sidebar-top">
            <button
              className="sidebar-logo"
              type="button"
              onClick={() => {
                if (!sidebarOpen) {
                  setSidebarOpen(true);
                }
              }}
              aria-label="Show Sidebar"
              title="Show Sidebar"
            >
              <img src="/smart-home.png" alt="Home Safety" />
            </button>
            {sidebarOpen && (
              <button
                className="sidebar-toggle"
                type="button"
                onClick={() => setSidebarOpen(false)}
                aria-label="Hide Sidebar"
                title="Hide Sidebar"
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <rect
                    x="4"
                    y="4"
                    width="16"
                    height="16"
                    rx="3"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                  />
                  <rect x="7" y="6.5" width="3.5" height="11" rx="1.2" fill="currentColor" />
                </svg>
              </button>
            )}
          </div>

          <div className="sidebar-scroll">
            <nav className="sidebar-nav">
              <button className="sidebar-link" type="button" onClick={handleNewChat}>
                <span className="icon-emoji" aria-hidden="true">
                  📝
                </span>
                <span>New report</span>
              </button>
              <button className="sidebar-link" type="button">
                <span className="icon-emoji" aria-hidden="true">
                  🔍
                </span>
                <span>Search chats</span>
              </button>
              <button className="sidebar-link" type="button">
                <span className="icon-emoji" aria-hidden="true">
                  ⚙️
                </span>
                <span>Settings</span>
              </button>
            </nav>

            <div className="sidebar-section">
              <div className="sidebar-header">
                <span>History</span>
                <button
                  className="sidebar-collapse-btn"
                  type="button"
                  onClick={() => setHistoryCollapsed((prev) => !prev)}
                  aria-label={historyCollapsed ? "Show history" : "Hide history"}
                  title={historyCollapsed ? "Show history" : "Hide history"}
                >
                  <span className="icon-emoji" aria-hidden="true">
                    {historyCollapsed ? "▸" : "▾"}
                  </span>
                </button>
              </div>
              <div className="sidebar-body">
                {isLoadingChats ? (
                  <div className="sidebar-empty">Loading...</div>
                ) : chats.length === 0 ? (
                  <div className="sidebar-empty">No history yet.</div>
                ) : (
                  !historyCollapsed && (
                    <div className="sidebar-history-list">
                      {chats.map((chat) => (
                        <div
                          className={`sidebar-history-item ${
                            chat.id === activeChatId ? "active" : ""
                          } ${chat.pinned ? "pinned" : ""}`}
                          key={chat.id || formatChatTitle(chat)}
                        >
                          <button
                            className="sidebar-history-button"
                            type="button"
                            onClick={() => handleSelectChat(chat.id)}
                            title={formatChatTitle(chat)}
                          >
                            <span className="sidebar-history-title">{formatChatTitle(chat)}</span>
                          </button>
                          <button
                            className="sidebar-history-menu"
                            type="button"
                            aria-label="Chat actions"
                            onClick={(event) => {
                              event.stopPropagation();
                              setOpenMenuId((prev) => (prev === chat.id ? null : chat.id));
                            }}
                          >
                          <span className="menu-icon menu-icon-dots" aria-hidden="true">
                            ...
                          </span>
                            <span className="menu-icon menu-icon-pin" aria-hidden="true">
                              📌
                            </span>
                          </button>
                          {openMenuId === chat.id && (
                            <div className="chat-menu" role="menu">
                              <button
                                className="chat-menu-item"
                                type="button"
                                onClick={() => {
                                  handleRenameChat(chat);
                                  setOpenMenuId(null);
                                }}
                              >
                                <span className="chat-menu-emoji" aria-hidden="true">
                                  ✏️
                                </span>
                                Rename
                              </button>
                              <button
                                className="chat-menu-item"
                                type="button"
                                onClick={() => {
                                  handleTogglePin(chat);
                                  setOpenMenuId(null);
                                }}
                              >
                                <span className="chat-menu-emoji" aria-hidden="true">📌</span>
                                {chat.pinned ? "Unpin chat" : "Pin chat"}
                              </button>
                              <button
                                className="chat-menu-item danger"
                                type="button"
                                onClick={() => {
                                  handleDeleteChat(chat);
                                  setOpenMenuId(null);
                                }}
                              >
                                <span className="chat-menu-emoji" aria-hidden="true">
                                  🗑️
                                </span>
                                Delete
                              </button>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )
                )}
              </div>
            </div>
          </div>

          <div className="sidebar-divider" />
          <button className="sidebar-user" type="button" onClick={handleProfile}>
            <div className="sidebar-user-avatar" aria-hidden="true">
              {avatarLetter}
            </div>
            <div className="sidebar-user-details">
              <div className="sidebar-user-name">{displayName}</div>
              {displayEmail ? <div className="sidebar-user-email">{displayEmail}</div> : null}
            </div>
          </button>
        </aside>

        <main className="content">
          {showMainPanels && (
            <>
              <section className="panel">
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
                                {risk?.risk || "Risk"} — {risk?.priority || "N/A"} —{" "}
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
                                {action?.action || "Action"} — {action?.budget || "N/A"} —{" "}
                                {action?.difficulty || "N/A"} — {action?.priority || "N/A"}
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
                                  {item?.item || "Item"} — {item?.priority || "N/A"}
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
                                {item?.action || "Action"} — {item?.priority || "N/A"} —{" "}
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
        </main>
        {previewImage ? (
          <div
            className="image-preview-overlay"
            role="dialog"
            aria-modal="true"
            onClick={() => setPreviewImage("")}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                setPreviewImage("");
              }
            }}
            tabIndex={-1}
          >
            <div className="image-preview-modal" onClick={(event) => event.stopPropagation()}>
              <button
                className="image-preview-close"
                type="button"
                onClick={() => setPreviewImage("")}
                aria-label="Close preview"
              >
                ×
              </button>
              <img src={previewImage} alt="Preview" />
            </div>
          </div>
        ) : null}
      </div>

      <div className="chat-input-bar">
        <div className="chat-input-inner">
          <textarea
            className="chat-input"
            rows={1}
            ref={chatInputRef}
            value={questionInput}
            onChange={(event) => setQuestionInput(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === "Enter" &&
                !event.shiftKey &&
                !event.isComposing
              ) {
                event.preventDefault();
                if (chatSendDisabled) {
                  return;
                }
                handleChat();
              }
            }}
            placeholder="Ask about hazards, lighting, or improvements..."
          />
          <button
            className="btn solid"
            type="button"
            disabled={chatSendDisabled}
            onClick={handleChat}
          >
            {chatPhase === "generating" ? "Generating..." : isChatting ? "Thinking..." : "Ask"}
          </button>
        </div>
      </div>
      {guideOpen ? (
        <div className="guide-modal-backdrop" role="dialog" aria-modal="true">
          <div className="guide-modal">
            <div className="guide-modal-header">
              <div>
                <div className="guide-modal-title">Quick Guide</div>
                <div className="guide-modal-subtitle">Safe-Scan Quick Guide</div>
              </div>
              <button className="btn ghost" type="button" onClick={handleCloseGuide}>
                Close
              </button>
            </div>
            <div className="guide-modal-body">
              {guideLoading ? (
                <div className="guide-modal-status">Loading...</div>
              ) : guideError ? (
                <div className="guide-modal-error">{guideError}</div>
              ) : (
                <div className="guide-modal-content">
                  {(guideSections || []).length === 0 ? (
                    <div className="guide-modal-status">No guide content available.</div>
                  ) : (
                    guideSections.map((section) => {
                      const isOpen = openGuideId === section.id;
                      return (
                        <div className="guide-section" key={section.id || section.title}>
                          <button
                            className={`guide-section-toggle ${isOpen ? "open" : ""}`}
                            type="button"
                            onClick={() =>
                              setOpenGuideId(isOpen ? "" : section.id)
                            }
                          >
                            <span>{section.title}</span>
                            <span className="guide-section-icon">{isOpen ? "−" : "+"}</span>
                          </button>
                          {isOpen ? (
                            <div className="guide-section-body">
                              {section.summary ? (
                                <p className="guide-section-summary">{section.summary}</p>
                              ) : null}
                              {Array.isArray(section.items) && section.items.length ? (
                                <ul className="guide-section-list">
                                  {section.items.map((item, idx) => (
                                    <li key={`${section.id}-item-${idx}`}>{item}</li>
                                  ))}
                                </ul>
                              ) : null}
                              {Array.isArray(section.steps) && section.steps.length ? (
                                <ol className="guide-section-steps">
                                  {section.steps.map((step, idx) => (
                                    <li key={`${section.id}-step-${idx}`}>{step}</li>
                                  ))}
                                </ol>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default HomePage;
