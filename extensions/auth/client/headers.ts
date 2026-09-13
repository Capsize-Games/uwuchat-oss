const ACCESS_TOKEN_KEY = "airunner_access_token";

export function getRequestHeaders(): Record<string, string> {
  const token = localStorage.getItem(ACCESS_TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}
