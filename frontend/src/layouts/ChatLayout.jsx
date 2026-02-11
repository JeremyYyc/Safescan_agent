import { useEffect, useRef, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import "../styles/home.css";

function ChatLayout({
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
  handleGoHome,
  handleSelectChat,
  handleRenameChat,
  handleDeleteChat,
  handleTogglePin,
  handleProfile,
  draftMode,
  authUser,
  chats,
  activeChatId,
  activeChatType,
  chatReportRefs,
  pendingReportIds,
  handleSelectPendingReports,
  reportChats,
  handleSearchReports,
  handleUploadPdfReport,
  isUploadingPdf,
  handleRunCompareSelection,
  handleRemovePendingReportSelection,
  handleRemoveReportRef,
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
  pdfExport,
  isPdfGenerating,
  handlePreviewPdf,
  handleDownloadPdf,
  handleRegeneratePdf,
  activeChatTitle,
  videoFile,
  setVideoFile,
  selectedVideoPath,
  fileInputRef,
  attributes,
  toggleAttribute,
  videoStatus,
  formatChatTitle,
}) {
  const ICON_HISTORY_REPORT = "\uD83D\uDD0D";
  const ICON_UPLOAD_PDF = "\uD83D\uDCC4";
  const navigate = useNavigate();
  const displayName = authUser?.username || authUser?.email || "User";
  const displayEmail = authUser?.email || "";
  const avatarLetter = displayName ? String(displayName).trim().charAt(0).toUpperCase() : "U";
  const [openMenuId, setOpenMenuId] = useState(null);
  const [historyCollapsed, setHistoryCollapsed] = useState(false);
  const [previewImage, setPreviewImage] = useState("");
  const [openGuideId, setOpenGuideId] = useState("");
  const [reportPickerOpen, setReportPickerOpen] = useState(false);
  const [selectedReportIds, setSelectedReportIds] = useState([]);
  const [attachmentMenuOpen, setAttachmentMenuOpen] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [reportSearchOpen, setReportSearchOpen] = useState(false);
  const [reportSearchKeyword, setReportSearchKeyword] = useState("");
  const [reportSearchLoading, setReportSearchLoading] = useState(false);
  const [reportSearchResults, setReportSearchResults] = useState([]);
  const [reportSearchError, setReportSearchError] = useState("");
  const chatInputRef = useRef(null);
  const uploadPdfInputRef = useRef(null);
  const reportSearchInputRef = useRef(null);
  const reportSearchSeqRef = useRef(0);
  const resolvedChatType = activeChatType || "report";
  const isBotChat = resolvedChatType === "bot";
  const isMainOnlyView = !activeChatId && !draftMode;
  const showReportPickerTrigger = isBotChat || isMainOnlyView;

  function autoHideSidebarOnMobile() {
    if (typeof window === "undefined" || !window.matchMedia) {
      return;
    }
    if (window.matchMedia("(max-width: 720px)").matches) {
      setSidebarOpen(false);
    }
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
      if (!target.closest(".chat-attach-wrap")) {
        setAttachmentMenuOpen(false);
      }
    }

    function handleKey(event) {
      if (event.key === "Escape") {
        setOpenMenuId(null);
        setAttachmentMenuOpen(false);
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

  useEffect(() => {
    if (!reportPickerOpen) {
      return;
    }
    const attachedSourceIds = (chatReportRefs || [])
      .filter((ref) => ref && ref.status !== "deleted" && ref.source_chat_id)
      .map((ref) => String(ref.source_chat_id))
      .filter((id) => Boolean(id));
    const merged = Array.from(new Set([...(pendingReportIds || []), ...attachedSourceIds]));
    setSelectedReportIds(merged);
  }, [reportPickerOpen, chatReportRefs, pendingReportIds]);

  useEffect(() => {
    if (!reportSearchOpen) {
      return undefined;
    }
    setReportSearchError("");
    const timer = window.setTimeout(() => {
      reportSearchInputRef.current?.focus();
    }, 20);
    function handleEsc(event) {
      if (event.key === "Escape") {
        setReportSearchOpen(false);
      }
    }
    window.addEventListener("keydown", handleEsc);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("keydown", handleEsc);
    };
  }, [reportSearchOpen]);

  useEffect(() => {
    if (!reportSearchOpen) {
      return undefined;
    }
    const timer = window.setTimeout(async () => {
      reportSearchSeqRef.current += 1;
      const seq = reportSearchSeqRef.current;
      setReportSearchLoading(true);
      setReportSearchError("");
      try {
        let nextItems = [];
        if (typeof handleSearchReports === "function") {
          nextItems = await handleSearchReports(reportSearchKeyword || "");
        } else {
          const normalized = String(reportSearchKeyword || "").trim().toLowerCase();
          nextItems = (reportChats || [])
            .filter((item) => {
              if (!normalized) {
                return true;
              }
              const title = String(item?.title || "").toLowerCase();
              return title.includes(normalized);
            })
            .map((item) => ({
              chat_id: item?.id,
              chat_title: item?.title || "",
              created_at: item?.created_at,
              updated_at: item?.updated_at,
              last_message_at: item?.last_message_at,
              report: null,
            }));
        }
        if (seq === reportSearchSeqRef.current) {
          setReportSearchResults(Array.isArray(nextItems) ? nextItems : []);
        }
      } catch (err) {
        if (seq === reportSearchSeqRef.current) {
          setReportSearchResults([]);
          setReportSearchError(err?.message || "Failed to search reports.");
        }
      } finally {
        if (seq === reportSearchSeqRef.current) {
          setReportSearchLoading(false);
        }
      }
    }, 220);
    return () => window.clearTimeout(timer);
  }, [reportSearchKeyword, reportSearchOpen, handleSearchReports, reportChats]);

  function resolveSearchItemTime(item) {
    const value =
      item?.report?.created_at ||
      item?.last_message_at ||
      item?.updated_at ||
      item?.created_at ||
      "";
    const timestamp = Date.parse(value);
    if (Number.isNaN(timestamp)) {
      return 0;
    }
    return timestamp;
  }

  function resolveSearchGroupLabel(timestamp) {
    if (!timestamp) {
      return "Earlier";
    }
    const now = new Date();
    const current = new Date(timestamp);
    const startNow = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startCurrent = new Date(
      current.getFullYear(),
      current.getMonth(),
      current.getDate()
    ).getTime();
    const diffDays = Math.floor((startNow - startCurrent) / 86400000);
    if (diffDays <= 0) {
      return "Today";
    }
    if (diffDays === 1) {
      return "Yesterday";
    }
    if (diffDays <= 7) {
      return "Previous 7 days";
    }
    return "Earlier";
  }

  const groupedSearchResults = (() => {
    const groups = new Map();
    (reportSearchResults || [])
      .slice()
      .sort((left, right) => resolveSearchItemTime(right) - resolveSearchItemTime(left))
      .forEach((item) => {
        const key = resolveSearchGroupLabel(resolveSearchItemTime(item));
        if (!groups.has(key)) {
          groups.set(key, []);
        }
        groups.get(key).push(item);
      });
    return Array.from(groups.entries());
  })();

  function formatSearchItemMeta(item) {
    const report = item?.report || null;
    const reportTitle = String(report?.title || "").trim();
    const summary = String(report?.summary || "").trim();
    const sourceType = String(report?.source_type || "").trim().toLowerCase();
    const sourceLabel = sourceType === "pdf" ? "PDF" : "Analysis";
    const timestamp = resolveSearchItemTime(item);
    const dateLabel = timestamp
      ? new Date(timestamp).toLocaleString([], {
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
        })
      : "";
    const parts = [reportTitle, summary, sourceLabel, dateLabel].filter(Boolean);
    return parts.join(" · ");
  }

  function highlightSearchKeyword(text) {
    const rawText = String(text || "");
    const keyword = String(reportSearchKeyword || "").trim();
    if (!rawText || !keyword) {
      return rawText;
    }
    const escapedKeyword = keyword.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    if (!escapedKeyword) {
      return rawText;
    }
    const pattern = new RegExp(`(${escapedKeyword})`, "ig");
    const chunks = rawText.split(pattern);
    if (chunks.length <= 1) {
      return rawText;
    }
    return chunks.map((chunk, index) => {
      if (chunk.toLowerCase() === keyword.toLowerCase()) {
        return (
          <mark className="search-modal-highlight" key={`search-highlight-${index}`}>
            {chunk}
          </mark>
        );
      }
      return <span key={`search-plain-${index}`}>{chunk}</span>;
    });
  }

  async function handlePdfInputChange(event) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    const name = String(file.name || "");
    const isPdfByName = name.toLowerCase().endsWith(".pdf");
    const isPdfByType =
      file.type === "application/pdf" || file.type === "application/x-pdf";
    if (!isPdfByName || !isPdfByType) {
      setUploadError("Only PDF files are supported.");
      return;
    }
    setUploadError("");
    try {
      await handleUploadPdfReport(file, activeChatId || null);
      setAttachmentMenuOpen(false);
    } catch (err) {
      setUploadError(err?.message || "Failed to upload PDF report.");
    }
  }

  const outletContext = {
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
    pdfExport,
    isPdfGenerating,
    handlePreviewPdf,
    handleDownloadPdf,
    handleRegeneratePdf,
    activeChatTitle,
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
    chatReportRefs,
    reportChats,
    pendingReportIds,
    handleRunCompareSelection,
    handleRemovePendingReportSelection,
    handleRemoveReportRef,
    setPreviewImage,
    setReportPickerOpen,
    handleSelectChat,
    handleNewChat,
    handleGoHome,
  };

  return (
    <div className={`page ${sidebarOpen ? "sidebar-open" : "sidebar-collapsed"}`}>
      <header className="topbar">
        <div className="brand">
          {!sidebarOpen && (
            <button
              className="mobile-sidebar-toggle"
              type="button"
              onClick={() => setSidebarOpen(true)}
              aria-label="Show Sidebar"
              title="Show Sidebar"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <rect x="3" y="5" width="18" height="2" rx="1" fill="currentColor" />
                <rect x="3" y="11" width="18" height="2" rx="1" fill="currentColor" />
                <rect x="3" y="17" width="18" height="2" rx="1" fill="currentColor" />
              </svg>
            </button>
          )}
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
        <div
          className={`sidebar-overlay ${sidebarOpen ? "open" : ""}`}
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
        <aside className="sidebar">
          <div className="sidebar-top">
            <button
              className="sidebar-logo"
              type="button"
              onClick={() => {
                if (!sidebarOpen) {
                  setSidebarOpen(true);
                  return;
                }
                handleGoHome();
                navigate("/chat");
              }}
              aria-label={sidebarOpen ? "Back to main view" : "Show Sidebar"}
              title={sidebarOpen ? "Back to main view" : "Show Sidebar"}
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
              <button
                className="sidebar-link"
                type="button"
                onClick={() => navigate("/report/new")}
              >
                <span className="icon-emoji" aria-hidden="true">
                  📑
                </span>
                <span>New report</span>
              </button>
              <button
                className="sidebar-link"
                type="button"
                onClick={() => {
                  setReportSearchOpen(true);
                  setReportSearchKeyword("");
                  setReportSearchError("");
                  setReportSearchResults([]);
                }}
              >
                <span className="icon-emoji" aria-hidden="true">
                  🔎
                </span>
                <span>Search report</span>
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
                            onClick={() => {
                              const target =
                                (chat.chat_type || "report") === "bot"
                                  ? `/chat/${chat.id}`
                                  : `/report/${chat.id}`;
                              navigate(target);
                              autoHideSidebarOnMobile();
                            }}
                            title={formatChatTitle(chat)}
                          >
                            <span className="sidebar-history-title">
                              {formatChatTitle(chat)}
                            </span>
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
                              ⋯
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
          <Outlet context={outletContext} />
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
          {showReportPickerTrigger ? (
            <div className="chat-attach-wrap">
              <button
                className="chat-plus-btn"
                type="button"
                onClick={() => setAttachmentMenuOpen((prev) => !prev)}
                title="Attach reports"
                aria-label="Attach reports"
              >
                +
              </button>
              {attachmentMenuOpen ? (
                <div className="chat-attach-menu" role="menu">
                  <button
                    className="chat-attach-item"
                    type="button"
                    onClick={() => {
                      setAttachmentMenuOpen(false);
                      setReportPickerOpen(true);
                    }}
                  >
                    <span className="icon-emoji" aria-hidden="true">
                      {ICON_HISTORY_REPORT}
                    </span>
                    <span>Select history report</span>
                  </button>
                  <button
                    className="chat-attach-item"
                    type="button"
                    onClick={() => uploadPdfInputRef.current?.click()}
                    disabled={isUploadingPdf}
                  >
                    <span className="icon-emoji" aria-hidden="true">
                      {ICON_UPLOAD_PDF}
                    </span>
                    <span>
                      {isUploadingPdf ? "Uploading PDF..." : "Upload report (PDF)"}
                    </span>
                  </button>
                  {uploadError ? (
                    <div className="chat-attach-error">{uploadError}</div>
                  ) : null}
                </div>
              ) : null}
              <input
                ref={uploadPdfInputRef}
                className="file-input file-input-hidden"
                type="file"
                accept="application/pdf,.pdf"
                onChange={handlePdfInputChange}
              />
            </div>
          ) : null}
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
      {reportSearchOpen ? (
        <div className="search-modal-backdrop" role="dialog" aria-modal="true" onClick={() => setReportSearchOpen(false)}>
          <div className="search-modal" onClick={(event) => event.stopPropagation()}>
            <div className="search-modal-header">
              <input
                ref={reportSearchInputRef}
                className="search-modal-input"
                type="text"
                value={reportSearchKeyword}
                onChange={(event) => setReportSearchKeyword(event.target.value)}
                placeholder="Search reports..."
              />
              <button
                className="search-modal-close"
                type="button"
                onClick={() => setReportSearchOpen(false)}
                aria-label="Close search"
              >
                ×
              </button>
            </div>
            <div className="search-modal-body">
              <button
                className="search-modal-new"
                type="button"
                onClick={() => {
                  setReportSearchOpen(false);
                  setReportSearchKeyword("");
                  navigate("/report/new");
                  autoHideSidebarOnMobile();
                }}
              >
                <span className="search-modal-item-icon" aria-hidden="true">
                  ＋
                </span>
                <span>New report</span>
              </button>
              {reportSearchLoading ? (
                <div className="search-modal-status">Searching...</div>
              ) : reportSearchError ? (
                <div className="search-modal-error">{reportSearchError}</div>
              ) : groupedSearchResults.length === 0 ? (
                <div className="search-modal-status">No matching reports.</div>
              ) : (
                groupedSearchResults.map(([groupLabel, items]) => (
                  <div className="search-modal-group" key={`group-${groupLabel}`}>
                    <div className="search-modal-group-title">{groupLabel}</div>
                    <div className="search-modal-group-list">
                      {items.map((item) => {
                        const chatId = String(item?.chat_id || "").trim();
                        const title = String(item?.chat_title || "").trim() || "Untitled report";
                        const meta = formatSearchItemMeta(item);
                        return (
                          <button
                            className="search-modal-item"
                            type="button"
                            key={`search-item-${chatId}-${meta}`}
                            onClick={() => {
                              if (!chatId) {
                                return;
                              }
                              setReportSearchOpen(false);
                              setReportSearchKeyword("");
                              navigate(`/report/${chatId}`);
                              autoHideSidebarOnMobile();
                            }}
                          >
                            <span className="search-modal-item-icon" aria-hidden="true">
                              💬
                            </span>
                            <span className="search-modal-item-texts">
                              <span className="search-modal-item-title">
                                {highlightSearchKeyword(title)}
                              </span>
                              {meta ? (
                                <span className="search-modal-item-meta">
                                  {highlightSearchKeyword(meta)}
                                </span>
                              ) : null}
                            </span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      ) : null}
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
      {reportPickerOpen ? (
        <div className="guide-modal-backdrop" role="dialog" aria-modal="true">
          <div className="guide-modal">
            <div className="guide-modal-header">
              <div>
                <div className="guide-modal-title">Select Reports</div>
                <div className="guide-modal-subtitle">Choose multiple reports to compare</div>
              </div>
              <button className="btn ghost" type="button" onClick={() => setReportPickerOpen(false)}>
                Close
              </button>
            </div>
            <div className="guide-modal-body">
              {(reportChats || []).length === 0 ? (
                <div className="guide-modal-status">No reports available.</div>
              ) : (
                <div className="guide-modal-content">
                  <ul className="guide-section-list">
                    {(reportChats || []).map((reportChat) => {
                      const checked = selectedReportIds.includes(reportChat.id);
                      return (
                        <li key={`report-select-${reportChat.id}`}>
                          <label>
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={(event) => {
                                const nextChecked = event.target.checked;
                                setSelectedReportIds((prev) => {
                                  if (nextChecked) {
                                    return prev.includes(reportChat.id)
                                      ? prev
                                      : [...prev, reportChat.id];
                                  }
                                  return prev.filter((id) => id !== reportChat.id);
                                });
                              }}
                            />
                            {reportChat.title || `Chat ${reportChat.id}`}
                          </label>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
            <div className="guide-modal-header">
              <button
                className="btn solid"
                type="button"
                disabled={selectedReportIds.length === 0}
                onClick={async () => {
                  if (selectedReportIds.length === 0) {
                    return;
                  }
                  const attachedSourceIds = new Set(
                    (chatReportRefs || [])
                      .filter((ref) => ref && ref.status !== "deleted" && ref.source_chat_id)
                      .map((ref) => String(ref.source_chat_id))
                      .filter((id) => Boolean(id))
                  );
                  const pendingOnly = [...new Set(selectedReportIds)].filter(
                    (sourceChatId) => !attachedSourceIds.has(sourceChatId)
                  );
                  setUploadError("");
                  try {
                    await handleSelectPendingReports(pendingOnly);
                    setReportPickerOpen(false);
                  } catch (err) {
                    setUploadError(err?.message || "Failed to select reports.");
                  }
                }}
              >
                Select
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default ChatLayout;
