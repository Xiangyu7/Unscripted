import {
  GameState,
  ResetResponse,
  SpeechSynthesisResponse,
  TurnResponse,
  VoiceStatusResponse,
  VoiceTurnResponse,
} from "./types";

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
  const resetData: ResetResponse = await res.json();
  if (resetData.game_state) {
    return resetData.game_state;
  }
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

export type StreamCallback = (event: {
  type: string;
  text?: string;
  character?: string;
  character_id?: string;
  voice?: string;
  speed?: number;
  url?: string;
  scene?: string;
  round?: number;
  phase?: string;
  tension?: number;
  game_over?: boolean;
  game_state?: GameState;
}) => void;

export async function submitTurnStream(
  sessionId: string,
  action: string,
  onEvent: StreamCallback,
): Promise<void> {
  const res = await fetch(`${API_URL}/api/turn/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, player_action: action }),
  });

  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Stream failed: ${res.status} ${errorText}`);
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body");

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("data: ")) {
        try {
          const event = JSON.parse(line.slice(6));
          onEvent(event);
        } catch {
          // Skip malformed events
        }
      }
    }
  }

  // Process any remaining data in the buffer after stream ends
  if (buffer.trim().startsWith("data: ")) {
    try {
      const event = JSON.parse(buffer.trim().slice(6));
      onEvent(event);
    } catch {
      // Skip malformed final event
    }
  }
}

export async function getPortraits(): Promise<Record<string, string>> {
  try {
    const res = await fetch(`${API_URL}/api/portraits`);
    if (!res.ok) return {};
    const data = await res.json();
    return data.portraits || {};
  } catch {
    return {};
  }
}

export async function getVoiceStatus(): Promise<VoiceStatusResponse> {
  const res = await fetch(`${API_URL}/api/voice/status`);
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to load voice status: ${res.status} ${errorText}`);
  }
  return res.json();
}

export async function submitVoiceTurn(
  sessionId: string,
  audio: Blob,
  filename = "voice-turn.wav"
): Promise<VoiceTurnResponse> {
  const formData = new FormData();
  formData.append("session_id", sessionId);
  formData.append("audio", audio, filename);

  const res = await fetch(`${API_URL}/api/voice/turn`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to submit voice turn: ${res.status} ${errorText}`);
  }
  return res.json();
}

export async function synthesizeSpeech(
  text: string,
  voice?: string,
  speed?: number
): Promise<SpeechSynthesisResponse> {
  const body: Record<string, unknown> = { text };
  if (voice) body.voice = voice;
  if (speed) body.speed = speed;
  const res = await fetch(`${API_URL}/api/voice/speak`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const errorText = await res.text();
    throw new Error(`Failed to synthesize speech: ${res.status} ${errorText}`);
  }
  return res.json();
}
