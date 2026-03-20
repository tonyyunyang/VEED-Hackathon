/**
 * Utility function to get the backend URL from environment variables
 * and sanitize it (trim, remove trailing slash).
 */
export function getBackendUrl(): string {
  const backendUrl = import.meta.env.VITE_BACKEND_TARGET;

  if (!backendUrl || typeof backendUrl !== "string") {
    return "";
  }

  let formattedUrl = backendUrl.trim();

  // Only process if it looks like a full URL.
  // If it's a relative path, we return it as is (or as empty string if preferred).
  if (formattedUrl.startsWith("http")) {
    if (formattedUrl.endsWith("/")) {
      formattedUrl = formattedUrl.slice(0, -1);
    }
    console.log("Backend URL:", formattedUrl);
    return formattedUrl;
  }

  return "";
}
