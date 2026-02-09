import { useEffect, useRef } from "react";
import { useOutletContext, useParams } from "react-router-dom";
import ThreadContent from "./ThreadContent.jsx";

function ChatThreadPage() {
  const { handleSelectChat } = useOutletContext();
  const { threadId } = useParams();
  const lastIdRef = useRef(null);

  useEffect(() => {
    if (!threadId) {
      return;
    }
    const normalized = String(threadId).trim();
    if (!normalized) {
      return;
    }
    if (lastIdRef.current === normalized) {
      return;
    }
    lastIdRef.current = normalized;
    void handleSelectChat(normalized);
  }, [threadId, handleSelectChat]);

  return <ThreadContent />;
}

export default ChatThreadPage;
