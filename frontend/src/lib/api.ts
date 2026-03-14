import { GameState, TurnResponse } from "./types";

function getApiUrl(): string {
  // 1. Build-time env var
  if (process.env.NEXT_PUBLIC_API_URL) return process.env.NEXT_PUBLIC_API_URL;
  // 2. Same origin (when behind reverse proxy, frontend and backend share same domain)
  if (typeof window !== "undefined") return window.location.origin;
  // 3. Fallback for local dev
  return "http://localhost:8000";
}

const API_URL = getApiUrl();

export async function resetGame(): Promise<GameState> {
  const res = await fetch(`${API_URL}/api/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to reset game: ${res.status} ${errorText}`);
  }
  const resetData = await res.json();
  const sessionId = resetData.session_id;
  return getState(sessionId);
}

export async function getState(sessionId: string): Promise<GameState> {
  const res = await fetch(`${API_URL}/api/state/${sessionId}`);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to get state: ${res.status} ${errorText}`);
  }
  return res.json();
}

export async function submitTurn(
  sessionId: string,
  action: string
): Promise<TurnResponse> {
  const res = await fetch(`${API_URL}/api/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, player_action: action }),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to submit turn: ${res.status} ${errorText}`);
  }
  return res.json();
}
