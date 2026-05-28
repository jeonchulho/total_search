const stripTrailingSlash = (value: string): string => value.replace(/\/$/, "");

export const config = {
  apiBaseUrl: stripTrailingSlash(import.meta.env.VITE_WEBHARD_API_BASE_URL || ""),
  appTitle: "Webhard Control Center",
};
