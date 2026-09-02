import { getLocale, setLocale, t } from "../i18n/index.js";

export default function LanguageSwitcher({ className = "btn ghost" }) {
  if (import.meta.env.VITE_ENABLE_LANGUAGE_SWITCH === "false") {
    return null;
  }

  const currentLocale = getLocale();
  const nextLocale = currentLocale === "zh-CN" ? "en-US" : "zh-CN";
  const label = currentLocale === "zh-CN" ? t("Switch to English") : t("Switch to Chinese");

  return (
    <button
      className={className}
      type="button"
      onClick={() => setLocale(nextLocale)}
      aria-label={label}
      title={label}
    >
      {label}
    </button>
  );
}
