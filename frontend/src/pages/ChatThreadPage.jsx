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
    const parsed = Number(threadId);
    if (Number.isNaN(parsed)) {
      return;
    }
    if (lastIdRef.current === parsed) {
      return;
    }
    lastIdRef.current = parsed;
    handleSelectChat(parsed);
  }, [threadId, handleSelectChat]);

  return <ThreadContent />;
}

export default ChatThreadPage;
