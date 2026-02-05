import { useEffect, useRef } from "react";
import { useOutletContext } from "react-router-dom";
import ThreadContent from "./ThreadContent.jsx";

function ReportNewPage() {
  const { handleNewChat } = useOutletContext();
  const didInitRef = useRef(false);

  useEffect(() => {
    if (didInitRef.current) {
      return;
    }
    didInitRef.current = true;
    handleNewChat();
  }, [handleNewChat]);

  return <ThreadContent />;
}

export default ReportNewPage;
