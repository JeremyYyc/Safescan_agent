import { useEffect, useRef, useState } from "react";
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import HomePage from "./pages/Home.jsx";
import LoginPage from "./pages/Login.jsx";
import ProfilePage from "./pages/Profile.jsx";
import RegisterPage from "./pages/Register.jsx";

const messagesPageSize = 200;
const authTokenKey = "safeScanAuthToken";
const authUserKey = "safeScanAuthUser";

const scoreLabels = [
  "personal_safety",
  "special_safety",
  "color_lighting",
  "psychological_impact",
  "final_socre",
];

const stepLabels = {
  extract_frames_start: "Extract frames",
  extract_frames_complete: "Frames extracted",
  filter_frames_start: "Filter frames",
  filter_frames_complete: "Frames filtered",
  select_representative_images_start: "Select representative images",
  select_representative_images_complete: "Representative images selected",
  yolo_detection_start: "YOLO detection",
  yolo_detection_complete: "YOLO detection complete",
  agent_pipeline_start: "Start agent pipeline",
  scene_agent_start: "Scene understanding",
  scene_agent_complete: "Scene understanding complete",
  hazard_agent_start: "Hazard identification",
  hazard_agent_complete: "Hazard identification complete",
  comfort_agent_complete: "Comfort analysis complete",
  compliance_agent_start: "Compliance checklist",
  compliance_agent_complete: "Compliance checklist complete",
  scoring_agent_complete: "Scoring complete",
  recommendation_agent_start: "Recommendations",
  recommendation_agent_complete: "Recommendations complete",
  report_writer_start: "Report drafting",
  report_writer_complete: "Report drafted",
  react_loop_start: "ReAct validation loop",
  react_loop_iteration_start: "ReAct iteration",
  react_loop_validation: "Validate report",
  react_loop_repair_instructions: "Generate repair instructions",
  react_loop_success: "Report validated",
  react_loop_max_iterations: "Reached max iterations",
  react_loop_complete: "ReAct loop complete",
  agent_pipeline_error: "Agent pipeline error",
  workflow_early_exit: "Workflow early exit",
};

const apiBase = import.meta.env.VITE_API_BASE || "";

function decodeTokenPayload(token) {
  if (!token) {
    return null;
  }
  const parts = token.split(".");
  if (parts.length < 1 || !parts[0]) {
    return null;
  }
  const base64 = parts[0].replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  try {
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    const text = new TextDecoder("utf-8").decode(bytes);
    const payload = JSON.parse(text);
    return typeof payload === "object" && payload ? payload : null;
  } catch {
    return null;
  }
}

function App() {
  const navigate = useNavigate();
  const [authToken, setAuthToken] = useState(() => localStorage.getItem(authTokenKey) || "");
  const [authUser, setAuthUser] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(authUserKey) || "null");
    } catch {
      return null;
    }
  });
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [profileLoading, setProfileLoading] = useState(false);
  const [loginForm, setLoginForm] = useState({ email: "", password: "" });
  const [registerForm, setRegisterForm] = useState({ email: "", username: "", password: "" });
  const [globalStatus, setGlobalStatus] = useState("Idle");
  const [videoStatus, setVideoStatus] = useState("No video uploaded.");
  const [chatStatus, setChatStatus] = useState("Ready.");
  const [images, setImages] = useState([]);
  const [regionStream, setRegionStream] = useState([]);
  const [regionVisible, setRegionVisible] = useState(false);
  const [reportData, setReportData] = useState(null);
  const [chatHistory, setChatHistory] = useState([]);
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [isLoadingChats, setIsLoadingChats] = useState(false);
  const [isLoadingMessages, setIsLoadingMessages] = useState(false);
  const [questionInput, setQuestionInput] = useState("");
  const [lastRegionInfo, setLastRegionInfo] = useState([]);
  const [chatVideoFiles, setChatVideoFiles] = useState({});
  const [chatVideoPaths, setChatVideoPaths] = useState({});
  const [isRunning, setIsRunning] = useState(false);
  const [activeChatHasReport, setActiveChatHasReport] = useState(false);
  const [isChatting, setIsChatting] = useState(false);
  const [chatPhase, setChatPhase] = useState("idle");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [guideOpen, setGuideOpen] = useState(false);
  const [guideLoading, setGuideLoading] = useState(false);
  const [guideSections, setGuideSections] = useState([]);
  const [guideError, setGuideError] = useState("");
  const [attributes, setAttributes] = useState({
    isPregnant: false,
    isChildren: false,
    isElderly: false,
    isDisabled: false,
    isAllergic: false,
    isPets: false,
  });

  const streamIdRef = useRef(0);
  const flowTimerRef = useRef(null);
  const flowBaseRef = useRef("");
  const fileInputRef = useRef(null);
  const chatEndRef = useRef(null);

  const activeVideoFile = activeChatId ? chatVideoFiles[activeChatId] || null : null;
  const activeVideoPath = activeChatId ? chatVideoPaths[activeChatId] || "" : "";
  const chatSendDisabled = isChatting || isRunning || !activeChatHasReport;

  function setActiveVideoFile(file) {
    if (!activeChatId) {
      return;
    }
    setChatVideoFiles((prev) => ({ ...prev, [activeChatId]: file || null }));
    if (file) {
      setChatVideoPaths((prev) => ({ ...prev, [activeChatId]: "" }));
    }
  }

  function clearFileInput() {
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  useEffect(() => {
    if (authToken) {
      void loadChatListOnly();
    } else {
      setChats([]);
      setActiveChatId(null);
      setChatHistory([]);
      setLastRegionInfo([]);
      setRegionStream([]);
      setRegionVisible(false);
      setReportData(null);
      setImages([]);
      setChatVideoPaths({});
      setActiveChatHasReport(false);
      clearFileInput();
    }
  }, [authToken]);

  useEffect(() => {
    const node = chatEndRef.current;
    if (!node) {
      return undefined;
    }
    const behavior = isChatting ? "smooth" : "auto";
    const raf = requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        node.scrollIntoView({ behavior, block: "end" });
      });
    });
    return () => cancelAnimationFrame(raf);
  }, [chatHistory, isChatting]);


  function normalizeRegionInfo(rawInfo) {
    if (typeof rawInfo === "string") {
      try {
        const parsed = JSON.parse(rawInfo);
        return { list: Array.isArray(parsed) ? parsed : [], rawText: Array.isArray(parsed) ? null : rawInfo };
      } catch {
        return { list: [], rawText: rawInfo };
      }
    }
    if (Array.isArray(rawInfo)) {
      return { list: rawInfo, rawText: null };
    }
    if (rawInfo && typeof rawInfo === "object") {
      return { list: [], rawText: JSON.stringify(rawInfo, null, 2) };
    }
    return { list: [], rawText: "" };
  }

  function normalizeReport(rawReport) {
    if (!rawReport) {
      return null;
    }
    if (typeof rawReport === "string") {
      try {
        const parsed = JSON.parse(rawReport);
        return parsed && typeof parsed === "object" ? parsed : null;
      } catch {
        return null;
      }
    }
    if (rawReport && typeof rawReport === "object") {
      return rawReport;
    }
    return null;
  }

  function normalizeMeta(rawMeta) {
    if (!rawMeta) {
      return null;
    }
    if (typeof rawMeta === "string") {
      try {
        const parsed = JSON.parse(rawMeta);
        return parsed && typeof parsed === "object" ? parsed : null;
      } catch {
        return null;
      }
    }
    if (rawMeta && typeof rawMeta === "object") {
      return rawMeta;
    }
    return null;
  }

  function persistAuth(token, user) {
    let resolvedUser = user || null;
    if (token) {
      localStorage.setItem(authTokenKey, token);
      setAuthToken(token);
      if (!resolvedUser) {
        const payload = decodeTokenPayload(token);
        if (payload) {
          resolvedUser = {
            user_id: payload.user_id,
            email: payload.email,
            username: payload.username,
          };
        }
      }
    }
    if (resolvedUser) {
      localStorage.setItem(authUserKey, JSON.stringify(resolvedUser));
      setAuthUser(resolvedUser);
    }
  }

  function clearAuth() {
    localStorage.removeItem(authTokenKey);
    localStorage.removeItem(authUserKey);
    setAuthToken("");
    setAuthUser(null);
  }

  async function apiFetch(url, options = {}) {
    if (!authToken) {
      throw new Error("Not authenticated.");
    }
    const headers = new Headers(options.headers || {});
    headers.set("Authorization", `Bearer ${authToken}`);
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
      clearAuth();
      throw new Error("Unauthorized.");
    }
    return response;
  }

  function formatChatTitle(chat) {
    if (!chat) {
      return "Untitled chat";
    }
    const title = String(chat.title || "").trim();
    if (title) {
      return title;
    }
    if (chat.id) {
      return `Chat ${chat.id}`;
    }
    return "Untitled chat";
  }

  function getChatTimestamp(chat) {
    if (!chat) {
      return 0;
    }
    const candidates = [
      chat.last_message_at,
      chat.updated_at,
      chat.created_at,
    ].filter(Boolean);
    if (candidates.length === 0) {
      return 0;
    }
    const timestamps = candidates
      .map((value) => Date.parse(value))
      .filter((value) => !Number.isNaN(value));
    return timestamps.length ? Math.max(...timestamps) : 0;
  }

  const sortedChats = [...chats].sort((a, b) => {
    const pinDiff = (b?.pinned ? 1 : 0) - (a?.pinned ? 1 : 0);
    if (pinDiff !== 0) {
      return pinDiff;
    }
    const diff = getChatTimestamp(b) - getChatTimestamp(a);
    if (diff !== 0) {
      return diff;
    }
    return (b?.id || 0) - (a?.id || 0);
  });

  async function fetchChats() {
    const res = await apiFetch(`${apiBase}/api/chats`);
    if (!res.ok) {
      throw new Error(await res.text());
    }
    const data = await res.json();
    return Array.isArray(data.chats) ? data.chats : [];
  }

  async function refreshChats() {
    try {
      const list = await fetchChats();
      setChats(list);
      return list;
    } catch (err) {
      setChatStatus(err.message || "Failed to load chats.");
      setChats([]);
      return [];
    }
  }

  async function updateChat(chatId, payload) {
    const res = await apiFetch(`${apiBase}/api/chats/${chatId}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload || {}),
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    const data = await res.json();
    if (data.chat) {
      setChats((prev) => prev.map((item) => (item.id === data.chat.id ? data.chat : item)));
    }
    return data.chat;
  }

  async function createChat(title) {
    const res = await apiFetch(`${apiBase}/api/chats`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(title ? { title } : {}),
    });
    if (!res.ok) {
      throw new Error(await res.text());
    }
    const data = await res.json();
    const chat = data.chat;
    if (chat) {
      setChats((prev) => [chat, ...prev.filter((item) => item.id !== chat.id)]);
      setActiveChatId(chat.id);
    }
    return chat;
  }

  async function loadChatMessages(chatId) {
    if (!chatId) {
      return;
    }
    setIsLoadingMessages(true);
    try {
      const res = await apiFetch(
        `${apiBase}/api/chats/${chatId}/messages?limit=${messagesPageSize}`
      );
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = await res.json();
      const messages = Array.isArray(data.messages) ? data.messages : [];
      const chatItems = messages
        .filter((item) => item.role === "user" || item.role === "assistant")
        .map((item) => ({
          id: item.id ?? `${item.role}-${item.created_at}`,
          role: item.role,
          content: item.content || "",
        }));
      setChatHistory(chatItems);

      const reportMessages = messages.filter((item) => item.role === "report");
      const hasReport = reportMessages.length > 0;
      setActiveChatHasReport(hasReport);
      const latestReport = reportMessages.length
        ? reportMessages[reportMessages.length - 1]
        : null;
      if (latestReport && latestReport.content) {
        const normalized = normalizeRegionInfo(latestReport.content);
        setLastRegionInfo(normalized.list);
        void streamRegionInfo(normalized);
        const meta = normalizeMeta(latestReport.meta);
        setReportData(normalizeReport(meta?.report));
        const repImages =
          (Array.isArray(meta?.representative_images) && meta.representative_images) ||
          (Array.isArray(meta?.representativeImages) && meta.representativeImages) ||
          [];
        setImages(repImages);
        if (meta?.video_path) {
          setChatVideoPaths((prev) => ({ ...prev, [chatId]: meta.video_path }));
        }
      } else {
        setLastRegionInfo([]);
        setRegionStream([]);
        setRegionVisible(false);
        setReportData(null);
        setImages([]);
        setActiveChatHasReport(false);
      }
    } catch (err) {
      setChatStatus(err.message || "Failed to load chat history.");
      setChatHistory([]);
      setActiveChatHasReport(false);
    } finally {
      setIsLoadingMessages(false);
    }
  }

  async function loadChatListOnly() {
    setIsLoadingChats(true);
    try {
      await refreshChats();
      setActiveChatId(null);
      setChatHistory([]);
      setLastRegionInfo([]);
      setRegionStream([]);
      setRegionVisible(false);
      setReportData(null);
      setImages([]);
      setChatVideoPaths({});
      setActiveChatHasReport(false);
      clearFileInput();
    } catch (err) {
      setChatStatus(err.message || "Failed to load chats.");
    } finally {
      setIsLoadingChats(false);
    }
  }

  async function handleLogin(event) {
    event.preventDefault();
    setAuthError("");
    setAuthLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(loginForm),
      });
      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || "Login failed");
      }
      const data = await res.json();
      persistAuth(data.token, data.user);
      navigate("/home", { replace: true });
    } catch (err) {
      setAuthError(err.message || "Login failed.");
    } finally {
      setAuthLoading(false);
    }
  }

  async function handleRegister(event) {
    event.preventDefault();
    setAuthError("");
    setAuthLoading(true);
    try {
      const res = await fetch(`${apiBase}/api/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(registerForm),
      });
      if (!res.ok) {
        let message = "Registration failed";
        try {
          const data = await res.json();
          if (data?.detail) {
            message = data.detail;
          }
        } catch {
          const text = await res.text();
          if (text) {
            message = text;
          }
        }
        if (res.status === 409 && /email/i.test(message)) {
          message = "This email has been registered.";
        }
        throw new Error(message);
      }
      const data = await res.json();
      persistAuth(data.token, data.user);
      navigate("/home", { replace: true });
    } catch (err) {
      setAuthError(err.message || "Registration failed.");
    } finally {
      setAuthLoading(false);
    }
  }

  function handleLogout() {
    clearAuth();
    navigate("/login", { replace: true });
  }

  async function handleOpenGuide() {
    setGuideOpen(true);
    if (guideSections.length || guideLoading) {
      return;
    }
    setGuideError("");
    setGuideLoading(true);
    try {
      const res = await apiFetch(`${apiBase}/api/guide`);
      if (!res.ok) {
        throw new Error(await res.text());
      }
      const data = await res.json();
      setGuideSections(Array.isArray(data.sections) ? data.sections : []);
    } catch (err) {
      setGuideError(err.message || "Failed to load guide.");
    } finally {
      setGuideLoading(false);
    }
  }

  function handleCloseGuide() {
    setGuideOpen(false);
  }

  async function handleProfileSave(username) {
    setProfileError("");
    setProfileLoading(true);
    try {
      const res = await apiFetch(`${apiBase}/api/auth/profile`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username }),
      });
      if (!res.ok) {
        let message = "Update failed";
        try {
          const data = await res.json();
          if (data?.detail) {
            message = data.detail;
          }
        } catch {
          const text = await res.text();
          if (text) {
            message = text;
          }
        }
        throw new Error(message);
      }
      const data = await res.json();
      persistAuth(data.token);
    } catch (err) {
      setProfileError(err.message || "Update failed.");
      throw err;
    } finally {
      setProfileLoading(false);
    }
  }

  async function handleSelectChat(chatId) {
    if (!chatId || chatId === activeChatId) {
      return;
    }
    setActiveChatId(chatId);
    setQuestionInput("");
    setChatHistory([]);
    setRegionStream([]);
    setRegionVisible(false);
      setReportData(null);
    setLastRegionInfo([]);
    setImages([]);
    setActiveChatHasReport(false);
    clearFileInput();
    await loadChatMessages(chatId);
  }

  async function handleNewChat() {
    setChatHistory([]);
    setRegionStream([]);
    setRegionVisible(false);
      setReportData(null);
    setLastRegionInfo([]);
    setImages([]);
    setActiveChatId(null);
    setQuestionInput("");
    setActiveChatHasReport(false);
    clearFileInput();
    try {
      const chat = await createChat();
      if (chat && chat.id) {
        await loadChatMessages(chat.id);
      }
    } catch (err) {
      setChatStatus(err.message || "Failed to create chat.");
    }
  }

  async function handleRenameChat(chat) {
    if (!chat?.id) {
      return;
    }
    const currentTitle = chat.title ? String(chat.title) : formatChatTitle(chat);
    const nextTitle = window.prompt("Rename chat", currentTitle);
    if (nextTitle === null) {
      return;
    }
    const trimmed = nextTitle.trim();
    if (!trimmed) {
      setChatStatus("Title cannot be empty.");
      return;
    }
    try {
      await updateChat(chat.id, { title: trimmed });
      await refreshChats();
    } catch (err) {
      setChatStatus(err.message || "Failed to rename chat.");
    }
  }

  async function handleTogglePin(chat) {
    if (!chat?.id) {
      return;
    }
    try {
      await updateChat(chat.id, { pinned: !chat.pinned });
      await refreshChats();
    } catch (err) {
      setChatStatus(err.message || "Failed to update pin.");
    }
  }

  async function handleDeleteChat(chat) {
    if (!chat?.id) {
      return;
    }
    const name = formatChatTitle(chat);
    const confirmed = window.confirm(`Delete "${name}"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
    try {
      const res = await apiFetch(`${apiBase}/api/chats/${chat.id}`, {
        method: "DELETE",
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      setChatVideoFiles((prev) => {
        if (!prev[chat.id]) {
          return prev;
        }
        const next = { ...prev };
        delete next[chat.id];
        return next;
      });
      setChatVideoPaths((prev) => {
        if (!prev[chat.id]) {
          return prev;
        }
        const next = { ...prev };
        delete next[chat.id];
        return next;
      });
      const remaining = await refreshChats();
      if (chat.id === activeChatId) {
        setActiveChatId(null);
        setChatHistory([]);
        setRegionStream([]);
        setRegionVisible(false);
      setReportData(null);
        setLastRegionInfo([]);
        setImages([]);
        setActiveChatHasReport(false);
        setQuestionInput("");
        clearFileInput();
        if (remaining.length > 0) {
          setActiveChatId(remaining[0].id);
          await loadChatMessages(remaining[0].id);
        } else {
          await handleNewChat();
        }
      }
    } catch (err) {
      setChatStatus(err.message || "Failed to delete chat.");
    }
  }

  async function ensureActiveChat() {
    if (activeChatId) {
      return activeChatId;
    }
    try {
      const chat = await createChat();
      return chat?.id || null;
    } catch (err) {
      setChatStatus(err.message || "Failed to create chat.");
      return null;
    }
  }

  function toUploadUrl(path) {
    if (!path) {
      return "";
    }
    const normalized = String(path).replace(/\\/g, "/");
    const match = normalized.match(/\/uploads\/.+/);
    if (match) {
      return `${apiBase}${match[0]}`;
    }
    const idx = normalized.indexOf("uploads/");
    if (idx !== -1) {
      return `${apiBase}/${normalized.substring(idx)}`;
    }
    return normalized;
  }

  function setFlowStatus(text, animate) {
    if (flowTimerRef.current) {
      clearInterval(flowTimerRef.current);
      flowTimerRef.current = null;
    }
    flowBaseRef.current = text;
    setVideoStatus(text);
    if (animate) {
      let tick = 0;
      flowTimerRef.current = setInterval(() => {
        tick += 1;
        const dots = ".".repeat((tick % 3) + 1);
        setVideoStatus(`${flowBaseRef.current}${dots}`);
      }, 350);
    }
  }

  function pause(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function appendFieldStream(regionIndex, label, value, streamId) {
    if (streamId !== streamIdRef.current) {
      return;
    }

    const normalizedValue =
      value && typeof value === "object" && !Array.isArray(value)
        ? JSON.stringify(value, null, 2)
        : value;

    const field = {
      label,
      value: normalizedValue,
      isList: Array.isArray(value),
    };

    setRegionStream((prev) =>
      prev.map((region, idx) =>
        idx === regionIndex ? { ...region, fields: [...region.fields, field] } : region
      )
    );
    await pause(90);
  }

  async function streamRegionInfo(rawInfo) {
    const normalized = rawInfo && rawInfo.list ? rawInfo : normalizeRegionInfo(rawInfo);
    const { list, rawText } = normalized;

    streamIdRef.current += 1;
    const streamId = streamIdRef.current;
    setRegionStream([]);

    if (!list.length && !rawText) {
      setRegionVisible(false);
      setReportData(null);
      return;
    }

    setRegionVisible(true);

    if (!list.length && rawText) {
      setRegionStream([{ title: "Region Info", fields: [{ label: "raw", value: rawText, isList: false }] }]);
      return;
    }

    for (let index = 0; index < list.length; index += 1) {
      if (streamId !== streamIdRef.current) {
        return;
      }

      const region = list[index];
      if (!region || typeof region !== "object") {
        setRegionStream((prev) => [
          ...prev,
          { title: `Region ${index + 1}`, fields: [{ label: "value", value: String(region), isList: false }] },
        ]);
        await pause(80);
        continue;
      }

      const regionName = Array.isArray(region.regionName)
        ? region.regionName.join(", ")
        : region.regionName || "";
      const titleText = regionName ? `Region ${index + 1}: ${regionName}` : `Region ${index + 1}`;

      const regionImages = Array.isArray(region.evidenceImages)
        ? region.evidenceImages
        : Array.isArray(region.evidence_images)
          ? region.evidence_images
          : Array.isArray(region.image_paths)
            ? region.image_paths
            : [];

      setRegionStream((prev) => [
        ...prev,
        { title: titleText, fields: [], images: regionImages },
      ]);
      await pause(120);

      await appendFieldStream(index, "regionName", region.regionName, streamId);
      await appendFieldStream(index, "potentialHazards", region.potentialHazards, streamId);
      await appendFieldStream(index, "specialHazards", region.specialHazards, streamId);
      await appendFieldStream(index, "colorAndLightingEvaluation", region.colorAndLightingEvaluation, streamId);
      await appendFieldStream(index, "suggestions", region.suggestions, streamId);

      if (Array.isArray(region.scores)) {
        const scoreList = region.scores.map((score, scoreIndex) => {
          const label = scoreLabels[scoreIndex] || `score_${scoreIndex + 1}`;
          return `${label}: ${score}`;
        });
        await appendFieldStream(index, "scores", scoreList, streamId);
      } else {
        await appendFieldStream(index, "scores", region.scores, streamId);
      }

      const knownKeys = new Set([
        "regionName",
        "potentialHazards",
        "specialHazards",
        "colorAndLightingEvaluation",
        "suggestions",
        "scores",
        "evidenceImages",
        "evidence_images",
        "image_paths",
      ]);
      for (const key of Object.keys(region)) {
        if (!knownKeys.has(key)) {
          await appendFieldStream(index, key, region[key], streamId);
        }
      }
    }
  }

  function formatStep(entry) {
    return stepLabels[entry.step] || entry.step || "Step";
  }

  async function handleRunAnalysis() {
    if (!activeVideoFile) {
      setVideoStatus("Please select a video file.");
      return;
    }
    if (activeChatHasReport) {
      setVideoStatus("Report already generated for this chat. Create a new report to analyze another video.");
      return;
    }

    const chatId = await ensureActiveChat();
    if (!chatId) {
      setVideoStatus("Chat is not available.");
      return;
    }

    streamIdRef.current += 1;
    setRegionStream([]);
    setRegionVisible(false);
      setReportData(null);
    setImages([]);

    setIsRunning(true);
    setGlobalStatus("Uploading video...");
    setFlowStatus("Video Uploading", true);

    try {
      const formData = new FormData();
      formData.append("file", activeVideoFile);

      const uploadRes = await apiFetch(`${apiBase}/api/uploadVideo`, {
        method: "POST",
        body: formData,
      });

      if (!uploadRes.ok) {
        const err = await uploadRes.text();
        throw new Error(err || "Upload failed");
      }

      const uploadData = await uploadRes.json();
      setGlobalStatus("Running analysis...");
      setFlowStatus("Running analysis", true);

      const streamRes = await apiFetch(`${apiBase}/api/processVideoStream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          video_path: uploadData.video_path,
          attributes,
          chat_id: chatId,
        }),
      });

      if (!streamRes.ok || !streamRes.body) {
        const err = await streamRes.text();
        throw new Error(err || "Analysis failed");
      }

      const reader = streamRes.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop();

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            continue;
          }
          let event;
          try {
            event = JSON.parse(trimmed);
          } catch {
            continue;
          }

          if (event.type === "trace" && event.entry) {
            setFlowStatus(formatStep(event.entry), true);
          }

          if (event.type === "complete" && event.result) {
            const normalized = normalizeRegionInfo(event.result.regionInfo || []);
            setLastRegionInfo(normalized.list);
            void streamRegionInfo(normalized);
            setReportData(normalizeReport(event.result.report));
            setImages(event.result.representativeImages || []);
            setActiveChatHasReport(true);
            if (event.result.video_path && chatId) {
              setChatVideoPaths((prev) => ({ ...prev, [chatId]: event.result.video_path }));
            }
            setFlowStatus("Complete", false);
            setGlobalStatus("Analysis complete.");
            void refreshChats();
          }

          if (event.type === "error") {
            setFlowStatus("Error", false);
            throw new Error(event.message || "Analysis failed");
          }
        }
      }
    } catch (err) {
      setGlobalStatus("Error.");
      setFlowStatus(err.message || String(err), false);
    } finally {
      setIsRunning(false);
    }
  }

  async function handleChat() {
    if (isChatting) {
      return;
    }
    if (isRunning) {
      setChatStatus("Report is still generating. Please wait.");
      return;
    }
    if (!activeChatHasReport) {
      setChatStatus("Generate a report before asking questions.");
      return;
    }
    const question = questionInput.trim();
    if (!question) {
      setChatStatus("Please enter a question.");
      return;
    }

    setIsChatting(true);
    setChatPhase("thinking");
    setChatStatus("Thinking...");

    try {
      const chatId = await ensureActiveChat();
      if (!chatId) {
        throw new Error("Chat is not available.");
      }

      const userMessageId = `local-user-${Date.now()}`;
      setChatHistory((prev) => [
        ...prev,
        { id: userMessageId, role: "user", content: question },
      ]);
      setQuestionInput("");

      const payload = {
        chat_id: chatId,
        message: question,
      };

      const res = await apiFetch(`${apiBase}/api/processChat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.text();
        throw new Error(err || "Chat failed");
      }

      const data = await res.json();
      const replyText = data.reply || "";

      const assistantId = `local-assistant-${Date.now()}`;
      setChatHistory((prev) => {
        return [...prev, { id: assistantId, role: "assistant", content: "" }];
      });
      setChatPhase("generating");

      let idx = 0;
      const step = 2;
      const interval = setInterval(() => {
        idx = Math.min(replyText.length, idx + step);
        const slice = replyText.slice(0, idx);
        setChatHistory((prev) => {
          return prev.map((item) =>
            item.id === assistantId ? { ...item, content: slice } : item
          );
        });
        if (idx >= replyText.length) {
          clearInterval(interval);
          setChatStatus("Done.");
          setChatPhase("idle");
          setIsChatting(false);
        }
      }, 22);
      void refreshChats();
    } catch (err) {
      setChatStatus(err.message || String(err));
      setChatPhase("idle");
      setIsChatting(false);
    }
  }

  function toggleAttribute(key) {
    setAttributes((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <Routes>
      <Route path="/" element={<Navigate to={authToken ? "/home" : "/login"} replace />} />
      <Route
        path="/login"
        element={
          authToken ? (
            <Navigate to="/home" replace />
          ) : (
            <LoginPage
              loginForm={loginForm}
              onEmailChange={(event) =>
                setLoginForm((prev) => ({ ...prev, email: event.target.value }))
              }
              onPasswordChange={(event) =>
                setLoginForm((prev) => ({ ...prev, password: event.target.value }))
              }
              authError={authError}
              authLoading={authLoading}
              onSubmit={handleLogin}
              onSwitch={() => {
                setAuthError("");
                navigate("/register");
              }}
            />
          )
        }
      />
      <Route
        path="/register"
        element={
          authToken ? (
            <Navigate to="/home" replace />
          ) : (
            <RegisterPage
              registerForm={registerForm}
              onEmailChange={(event) =>
                setRegisterForm((prev) => ({ ...prev, email: event.target.value }))
              }
              onUsernameChange={(event) =>
                setRegisterForm((prev) => ({ ...prev, username: event.target.value }))
              }
              onPasswordChange={(event) =>
                setRegisterForm((prev) => ({ ...prev, password: event.target.value }))
              }
              authError={authError}
              authLoading={authLoading}
              onSubmit={handleRegister}
              onSwitch={() => {
                setAuthError("");
                navigate("/login");
              }}
            />
          )
        }
      />
      <Route
        path="/home"
        element={
          authToken ? (
              <HomePage
                sidebarOpen={sidebarOpen}
                setSidebarOpen={setSidebarOpen}
                handleLogout={handleLogout}
                handleOpenGuide={handleOpenGuide}
                guideOpen={guideOpen}
                guideLoading={guideLoading}
                guideSections={guideSections}
                guideError={guideError}
                handleCloseGuide={handleCloseGuide}
                handleNewChat={handleNewChat}
              handleSelectChat={handleSelectChat}
              handleRenameChat={handleRenameChat}
              handleDeleteChat={handleDeleteChat}
              handleTogglePin={handleTogglePin}
              handleProfile={() => {
                setProfileError("");
                navigate("/profile");
              }}
              authUser={authUser}
              chats={sortedChats}
              activeChatId={activeChatId}
              isLoadingChats={isLoadingChats}
              isLoadingMessages={isLoadingMessages}
              chatHistory={chatHistory}
              chatEndRef={chatEndRef}
              questionInput={questionInput}
              setQuestionInput={setQuestionInput}
              handleChat={handleChat}
              isChatting={isChatting}
              chatPhase={chatPhase}
              chatSendDisabled={chatSendDisabled}
              regionVisible={regionVisible}
              regionStream={regionStream}
              reportData={reportData}
              images={images}
              toUploadUrl={toUploadUrl}
              handleRunAnalysis={handleRunAnalysis}
              isRunning={isRunning}
              reportLocked={activeChatHasReport}
                videoFile={activeVideoFile}
                setVideoFile={setActiveVideoFile}
                selectedVideoPath={activeVideoPath}
                fileInputRef={fileInputRef}
                attributes={attributes}
                toggleAttribute={toggleAttribute}
                videoStatus={videoStatus}
                formatChatTitle={formatChatTitle}
            />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route
        path="/profile"
        element={
          authToken ? (
            <ProfilePage
              authUser={authUser}
              onBack={() => navigate("/home")}
              onSave={handleProfileSave}
              saving={profileLoading}
              error={profileError}
            />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      />
      <Route path="*" element={<Navigate to={authToken ? "/home" : "/login"} replace />} />
    </Routes>
  );
}

export default App;
