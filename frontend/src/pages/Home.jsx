import "../styles/home.css";

function HomePage({
  sidebarOpen,
  setSidebarOpen,
  resetSession,
  handleLogout,
  handleNewChat,
  handleSelectChat,
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
  regionVisible,
  regionStream,
  images,
  toUploadUrl,
  handleRunAnalysis,
  isRunning,
  videoFile,
  setVideoFile,
  fileInputRef,
  attributes,
  toggleAttribute,
  videoStatus,
  formatChatTitle,
}) {
  const displayName = authUser?.username || authUser?.email || "User";
  const displayEmail = authUser?.email || "";
  const avatarLetter = displayName ? String(displayName).trim().charAt(0).toUpperCase() : "U";

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
          <button className="btn ghost" type="button">
            Quick Guide
          </button>
          <button className="btn ghost" type="button" onClick={handleLogout}>
            Log out
          </button>
          <button className="btn solid" type="button" onClick={resetSession}>
            Reset Session
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
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M6 18l8.8-8.8a2 2 0 0 1 2.8 2.8L8.8 20H6v-2z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinejoin="round"
                  />
                  <path d="M14.5 7.5l2 2" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
                <span>New chat</span>
              </button>
              <button className="sidebar-link" type="button">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <circle cx="11" cy="11" r="6" fill="none" stroke="currentColor" strokeWidth="1.5" />
                  <path d="M16.5 16.5L20 20" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                </svg>
                <span>Search chats</span>
              </button>
              <button className="sidebar-link" type="button">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path
                    d="M12 8.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7zm8 3.5l-1.7-.3a6.8 6.8 0 0 0-.8-1.9l1-1.4-1.9-1.9-1.4 1a6.8 6.8 0 0 0-1.9-.8L12 4 10.7 5.7a6.8 6.8 0 0 0-1.9.8l-1.4-1-1.9 1.9 1 1.4a6.8 6.8 0 0 0-.8 1.9L4 12l1.7.3a6.8 6.8 0 0 0 .8 1.9l-1 1.4 1.9 1.9 1.4-1a6.8 6.8 0 0 0 1.9.8L12 20l1.3-1.7a6.8 6.8 0 0 0 1.9-.8l1.4 1 1.9-1.9-1-1.4a6.8 6.8 0 0 0 .8-1.9L20 12z"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.2"
                    strokeLinejoin="round"
                  />
                </svg>
                <span>Settings</span>
              </button>
            </nav>

            <div className="sidebar-section">
              <div className="sidebar-header">
                <span>History</span>
              </div>
              <div className="sidebar-body">
                {isLoadingChats ? (
                  <div className="sidebar-empty">Loading...</div>
                ) : chats.length === 0 ? (
                  <div className="sidebar-empty">No history yet.</div>
                ) : (
                  <div className="sidebar-history-list">
                    {chats.map((chat) => (
                      <button
                        className={`sidebar-history-item ${
                          chat.id === activeChatId ? "active" : ""
                        }`}
                        type="button"
                        key={chat.id || formatChatTitle(chat)}
                        onClick={() => handleSelectChat(chat.id)}
                      >
                        <span className="sidebar-history-title">{formatChatTitle(chat)}</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>

          <div className="sidebar-user">
            <div className="sidebar-user-avatar" aria-hidden="true">
              {avatarLetter}
            </div>
            <div className="sidebar-user-details">
              <div className="sidebar-user-name">{displayName}</div>
              {displayEmail ? <div className="sidebar-user-email">{displayEmail}</div> : null}
            </div>
            <button className="sidebar-user-action" type="button" onClick={handleProfile}>
              Profile
            </button>
          </div>
        </aside>

        <main className="content">
          <section className="panel">
            <header className="panel-header">
              <h2>Video Analysis</h2>
              <span className="panel-tag">Workflow</span>
            </header>

            <div className="panel-section">
              <label className="label">Upload video file</label>
              <input
                className="file-input"
                type="file"
                accept="video/*"
                ref={fileInputRef}
                onChange={(event) => setVideoFile(event.target.files?.[0] || null)}
              />
              {videoFile ? <div className="file-name">{videoFile.name}</div> : null}
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

            <button className="btn solid full" type="button" disabled={isRunning} onClick={handleRunAnalysis}>
              {isRunning ? videoStatus : "Run Analysis"}
            </button>

            <div className="panel-section">
              <label className="label">Representative images</label>
              <div className="image-grid">
                {images.map((path, idx) => (
                  <img key={`${path}-${idx}`} src={toUploadUrl(path)} alt="Representative" />
                ))}
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
                    <div className="region-title">{region.title}</div>
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
            </section>
          )}
          {chatHistory.length > 0 && (
            <section className="chat-stream">
              <div className="chat-thread">
                {chatHistory.map((item) => (
                  <div className={`chat-item ${item.role}`} key={item.id || `${item.role}-${item.content}`}>
                    <div className={`chat-message ${item.role}`}>{item.content}</div>
                  </div>
                ))}
                <div ref={chatEndRef} />
              </div>
            </section>
          )}
          {isLoadingMessages && chatHistory.length === 0 && (
            <section className="chat-stream">
              <div className="chat-empty">Loading chat...</div>
            </section>
          )}
        </main>
      </div>

      <div className="chat-input-bar">
        <div className="chat-input-inner">
          <input
            className="chat-input"
            type="text"
            value={questionInput}
            onChange={(event) => setQuestionInput(event.target.value)}
            placeholder="Ask about hazards, lighting, or improvements..."
          />
          <button className="btn solid" type="button" disabled={isChatting} onClick={handleChat}>
            {isChatting ? "Thinking..." : "Ask"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default HomePage;
