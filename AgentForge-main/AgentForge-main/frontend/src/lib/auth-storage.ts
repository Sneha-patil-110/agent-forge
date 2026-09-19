const TOKEN_KEY = "agentforge_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token: string): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
  } catch {
  }
}

export function clearStoredToken(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
  }
}
