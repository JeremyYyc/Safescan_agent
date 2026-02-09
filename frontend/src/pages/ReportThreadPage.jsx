import { useEffect, useRef } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router-dom";
import ThreadContent from "./ThreadContent.jsx";

function ReportThreadPage() {
  const { handleSelectChat } = useOutletContext();
  const { threadId } = useParams();
  const navigate = useNavigate();
  const lastIdRef = useRef(null);
  const requestSeqRef = useRef(0);

  useEffect(() => {
    if (!threadId) {
      return;
    }
    const normalized = String(threadId).trim();
    if (!normalized) {
      navigate("/report/new", { replace: true });
      return;
    }
    if (lastIdRef.current === normalized) {
      return;
    }
    lastIdRef.current = normalized;
    requestSeqRef.current += 1;
    const currentSeq = requestSeqRef.current;
    void (async () => {
      const result = await handleSelectChat(normalized);
      if (currentSeq !== requestSeqRef.current) {
        return;
      }
      if (result?.notFound) {
        navigate("/report/new", { replace: true });
      }
    })();
  }, [threadId, handleSelectChat, navigate]);

  return <ThreadContent />;
}

export default ReportThreadPage;
