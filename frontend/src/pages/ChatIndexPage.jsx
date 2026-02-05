import { useEffect, useRef } from "react";
import { useOutletContext } from "react-router-dom";

function ChatIndexPage() {
  const { handleGoHome } = useOutletContext();
  const didInitRef = useRef(false);

  useEffect(() => {
    if (didInitRef.current) {
      return;
    }
    didInitRef.current = true;
    handleGoHome();
  }, [handleGoHome]);

  return null;
}

export default ChatIndexPage;
