"use client";

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BrowserWavRecorder } from "@/lib/audio";
import { AmbientAudioManager } from "@/lib/ambient";
import {
  getMoodPortraits,
  getPortraits,
  getVoiceStatus,
  resetGame,
  submitTurn,
  submitTurnStream,
  submitVoiceTurn,
  synthesizeSpeech,
  API_URL,
} from "@/lib/api";
import GameBoard from "@/components/GameBoard";
import StoryFeed from "@/components/StoryFeed";
import CharacterPanel from "@/components/CharacterPanel";
import CluePanel from "@/components/CluePanel";
import WorldLedger from "@/components/WorldLedger";
import QuickActions from "@/components/QuickActions";
import DetectiveNotebook from "@/components/DetectiveNotebook";
import LocationMap from "@/components/LocationMap";
import CaseReport from "@/components/CaseReport";
import {
  FeedItem,
  GameState,
  TurnResponse,
  VoiceStatusResponse,
} from "@/lib/types";

let feedCounter = 0;
function nextFeedId(): string {
  feedCounter += 1;
  return `feed-${feedCounter}-${Date.now()}`;
}

function getVoteOptionLabel(state: GameState | null, optionId: string): string {
  return (
    state?.vote_state?.options.find((option) => option.id === optionId)?.label ||
    optionId
  );
}

function formatPlayerAction(action: string, state: GameState | null): string {
  const trimmed = action.trim();
  if (trimmed.startsWith("投票:")) {
    const optionId = trimmed.slice("投票:".length).trim();
    return `投票给：${getVoteOptionLabel(state, optionId)}`;
  }
  return trimmed;
}

function getTurnFeedItems(turnResult: TurnResponse): FeedItem[] {
  const newFeed: FeedItem[] = [];

  if (turnResult.scene_image) {
    newFeed.push({
      id: nextFeedId(),
      type: "scene_image",
      text: turnResult.scene,
      imageUrl: turnResult.scene_image,
    });
  }

  if (turnResult.system_narration) {
    newFeed.push({
      id: nextFeedId(),
      type: "system",
      text: turnResult.system_narration,
    });
  }

  if (turnResult.director_note) {
    newFeed.push({
      id: nextFeedId(),
      type: "director",
      text: turnResult.director_note,
    });
  }

  for (const reply of turnResult.npc_replies || []) {
    newFeed.push({
      id: nextFeedId(),
      type: "npc",
      text: reply.text,
      character: reply.character_name,
    });
  }

  for (const statement of turnResult.public_statements || []) {
    newFeed.push({
      id: nextFeedId(),
      type: "npc",
      text: `【公开发言】${statement.text}`,
      character: statement.character_name,
    });
  }

  for (const evt of turnResult.npc_events || []) {
    newFeed.push({
      id: nextFeedId(),
      type: "event",
      text: evt.text,
    });
  }

  for (const record of turnResult.vote_records || []) {
    newFeed.push({
      id: nextFeedId(),
      type: "event",
      text: `【投票】${record.voter_name} -> ${record.target_label}\n${record.reason}`,
    });
  }

  for (const clue of turnResult.new_clues || []) {
    newFeed.push({
      id: nextFeedId(),
      type: "clue",
      text: clue,
    });
  }

  if (turnResult.game_over && turnResult.ending) {
    newFeed.push({
      id: nextFeedId(),
      type: "ending",
      text: turnResult.ending,
    });
  }

  return newFeed;
}

function updateGameStateFromTurn(
  prev: GameState | null,
  turnResult: TurnResponse
): GameState | null {
  if (turnResult.game_state) {
    return turnResult.game_state;
  }
  if (!prev) {
    return prev;
  }
  return {
    ...prev,
    round: turnResult.round,
    phase: turnResult.phase,
    tension: turnResult.tension,
    scene: turnResult.scene,
    game_over: turnResult.game_over,
    ending: turnResult.ending,
  };
}

interface SpeechSegment {
  text: string;
  voice?: string;
  isNarration?: boolean;
  speed?: number;
}

function buildSpeechSegments(turnResult: TurnResponse): SpeechSegment[] {
  const segments: SpeechSegment[] = [];
  const narratorVoice = turnResult.narrator_voice || "luodo";

  // System narration: narrator voice, slower than characters to create contrast
  if (turnResult.system_narration && turnResult.system_narration.length > 10) {
    segments.push({
      text: turnResult.system_narration,
      voice: narratorVoice,
      isNarration: true,
      speed: 1.15,
    });
  }

  // NPC replies: each character has their own voice + emotion speed
  for (const reply of turnResult.npc_replies || []) {
    segments.push({
      text: reply.text,
      voice: reply.voice ?? undefined,
      speed: reply.speed ?? 1.1,
    });
  }

  // Public statements: narrator voice, brisk
  for (const statement of turnResult.public_statements || []) {
    segments.push({
      text: statement.text,
      voice: narratorVoice,
      speed: 1.2,
    });
  }

  // Ending: narrator voice, slightly slower for gravitas
  if (turnResult.ending) {
    segments.push({
      text: turnResult.ending,
      voice: narratorVoice,
      isNarration: true,
      speed: 1.1,
    });
  }

  return segments;
}

function getPreferredBrowserVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) {
    return null;
  }
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((voice) => voice.lang.toLowerCase().startsWith("zh-cn")) ||
    voices.find((voice) => voice.lang.toLowerCase().startsWith("zh")) ||
    null
  );
}

export default function HomePage() {
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [portraits, setPortraits] = useState<Record<string, string>>({});
  const [moodPortraits, setMoodPortraits] = useState<Record<string, Record<string, string>>>({});
  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [caseReportData, setCaseReportData] = useState<any>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isVoiceSubmitting, setIsVoiceSubmitting] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatusResponse | null>(null);
  const [voicePlaybackEnabled, setVoicePlaybackEnabled] = useState(true);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [sidebarTab, setSidebarTab] = useState<"characters" | "info">("characters");
  const inputRef = useRef<HTMLInputElement>(null);
  const recorderRef = useRef<BrowserWavRecorder | null>(null);
  const audioPlaybackRef = useRef<HTMLAudioElement | null>(null);
  const ambientRef = useRef<AmbientAudioManager | null>(null);
  const initializedRef = useRef(false);

  const voteState = gameState?.vote_state ?? null;
  const isAwaitingVote = voteState?.status === "awaiting_player_vote";
  const checkpointState = gameState?.checkpoint_state ?? null;
  const isAwaitingCheckpoint = checkpointState?.status === "awaiting_hypothesis";
  const confrontationState = gameState?.confrontation_state ?? null;
  const isAwaitingConfrontation = confrontationState?.status === "awaiting_player_choice";
  const isInteractiveBlocked = isAwaitingVote || isAwaitingCheckpoint || isAwaitingConfrontation;
  const isBusy = isLoading || isVoiceSubmitting;
  const canUseVoiceInput =
    !!voiceStatus?.asr.available &&
    !!gameState &&
    !gameState.game_over &&
    !isInteractiveBlocked &&
    !isBusy;

  // Static portrait base path (works with Next.js basePath in prod)
  const portraitBase = (process.env.NODE_ENV === "production" ? "/Unscripted" : "") + "/portraits";

  // Memoize characters with mood-aware portrait URLs
  const charactersWithPortraits = useMemo(
    () => (gameState?.characters || []).map(c => {
      const validMoods = ["calm", "guarded", "nervous", "fearful", "angry", "desperate"];
      const mood = validMoods.includes(c.mood || "") ? c.mood! : "calm";
      // 1. Static pre-generated portrait (fastest, no API call)
      const staticUrl = `${portraitBase}/${c.id}_${mood}.png`;
      // 2. API-fetched mood portrait
      const moodUrl = moodPortraits[c.id]?.[mood];
      // 3. API-fetched default portrait
      const fallbackUrl = portraits[c.id];
      return {
        ...c,
        portrait_url: c.portrait_url || staticUrl || moodUrl || fallbackUrl,
      };
    }),
    [gameState?.characters, portraits, moodPortraits, portraitBase]
  );

  const addFeedItems = useCallback((items: FeedItem[]) => {
    setFeedItems((prev) => [...prev, ...items]);
  }, []);

  const stopPlayback = useCallback(() => {
    if (audioPlaybackRef.current) {
      audioPlaybackRef.current.pause();
      audioPlaybackRef.current.src = "";
      audioPlaybackRef.current = null;
    }
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  }, []);

  const speakWithBrowser = useCallback(
    (text: string) => {
      if (
        typeof window === "undefined" ||
        !("speechSynthesis" in window) ||
        !text.trim()
      ) {
        return;
      }

      stopPlayback();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "zh-CN";
      utterance.rate = 1.02;
      utterance.pitch = 1;
      const voice = getPreferredBrowserVoice();
      if (voice) {
        utterance.voice = voice;
      }
      window.speechSynthesis.speak(utterance);
    },
    [stopPlayback]
  );

  const speakTurn = useCallback(
    async (turnResult: TurnResponse) => {
      if (!voicePlaybackEnabled) {
        return;
      }

      const segments = buildSpeechSegments(turnResult);
      if (segments.length === 0) {
        return;
      }

      if (voiceStatus?.tts.available) {
        try {
          stopPlayback();

          for (let i = 0; i < segments.length; i++) {
            const segment = segments[i];

            // Synthesize with character-specific voice and speed
            const speech = await synthesizeSpeech(segment.text, segment.voice, segment.speed);

            // Create audio and wait for it to fully load before playing
            const audio = new Audio();
            audioPlaybackRef.current = audio;

            await new Promise<void>((resolve, reject) => {
              audio.onended = () => {
                audio.src = "";
                resolve();
              };
              audio.onerror = () => {
                audio.src = "";
                reject(new Error("Audio playback failed"));
              };

              // Set source and play only after canplaythrough
              audio.oncanplaythrough = () => {
                audio.play().catch(reject);
              };

              audio.src = `data:${speech.mime_type};base64,${speech.audio_base64}`;
              audio.load();
            });

            // Pause between speakers — longer between different voice types
            if (i < segments.length - 1) {
              const nextSegment = segments[i + 1];
              const isSpeakerChange = segment.voice !== nextSegment.voice;
              const pauseMs = isSpeakerChange ? 600 : 300;
              await new Promise((r) => setTimeout(r, pauseMs));
            }
          }
          return;
        } catch (err) {
          const errorMessage = err instanceof Error ? err.message : "未知错误";
          setVoiceError(`服务端播报失败，已切回浏览器播报：${errorMessage}`);
        }
      }

      // Browser fallback
      const fullText = segments.map((s) => s.text).join("\n\n");
      speakWithBrowser(fullText);
    },
    [speakWithBrowser, stopPlayback, voicePlaybackEnabled, voiceStatus]
  );

  const applyTurnResult = useCallback(
    (turnResult: TurnResponse) => {
      addFeedItems(getTurnFeedItems(turnResult));
      setGameState((prev) => updateGameStateFromTurn(prev, turnResult));
    },
    [addFeedItems]
  );

  const initializeVoice = useCallback(async () => {
    try {
      const status = await getVoiceStatus();
      setVoiceStatus(status);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "未知错误";
      setVoiceStatus({
        asr: {
          provider: "disabled",
          model: null,
          available: false,
          detail: "语音服务状态读取失败。",
          fallback: null,
        },
        tts: {
          provider: "disabled",
          model: null,
          available: false,
          detail: "服务端播报不可用，将使用浏览器播报。",
          fallback: "browser",
        },
      });
      setVoiceError(`语音服务状态读取失败：${errorMessage}`);
    }
  }, []);

  const initializeGame = useCallback(async () => {
    setIsLoading(true);
    setFeedItems([]);
    feedCounter = 0;
    stopPlayback();
    setVoiceError(null);

    try {
      const state = await resetGame();
      setGameState(state);

      // Fetch portraits in background (don't block game start)
      // Fetch default portraits immediately, then mood variants in background
      getPortraits().then((p) => {
        if (Object.keys(p).length > 0) {
          setPortraits(p);
        }
      });
      getMoodPortraits().then((mp) => {
        if (Object.keys(mp).length > 0) {
          setMoodPortraits(mp);
        }
      });

      const initialFeed: FeedItem[] = [
        // Game title
        {
          id: nextFeedId(),
          type: "system",
          text: `${state.title}`,
        },
        // Player role introduction
        {
          id: nextFeedId(),
          type: "director",
          text: "你的身份：受邀参加顾家晚宴的私人侦探。\n\n"
            + "你的任务：顾家继承人顾言在晚宴中途神秘失踪。你需要在天亮前（20轮内）查明真相。\n\n"
            + "你可以做任何事：搜查房间、审问嫌疑人、偷看手机、翻抽屉、关灯制造混乱……自由发挥。\n\n"
            + "三位嫌疑人：\n"
            + "  林岚 — 顾家秘书，冷静克制，似乎知道什么\n"
            + "  周牧 — 顾言发小，表面随和，暗藏紧张\n"
            + "  宋知微 — 记者，敏锐多疑，为何恰好在场？",
        },
      ];

      // Opening event
      for (const evt of state.events || []) {
        initialFeed.push({
          id: nextFeedId(),
          type: "event",
          text: evt.text,
        });
      }

      // Prompt to start
      initialFeed.push({
        id: nextFeedId(),
        type: "director",
        text: "调查开始。你现在站在宴会厅里，三位嫌疑人就在你面前。你想先做什么？",
      });

      addFeedItems(initialFeed);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "未知错误";
      addFeedItems([
        {
          id: nextFeedId(),
          type: "system",
          text: `连接失败: ${errorMessage}\n\n请确保后端服务已启动 (http://localhost:8000)`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  }, [addFeedItems, stopPlayback]);

  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;
    initializeGame();
    initializeVoice();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto-clear voice errors after 5 seconds
  useEffect(() => {
    if (!voiceError) return;
    const timer = setTimeout(() => setVoiceError(null), 5000);
    return () => clearTimeout(timer);
  }, [voiceError]);

  useEffect(() => {
    return () => {
      stopPlayback();
      const recorder = recorderRef.current;
      if (recorder) {
        void recorder.dispose();
      }
      if (ambientRef.current) {
        ambientRef.current.dispose();
      }
    };
  }, [stopPlayback]);

  const handleSubmitAction = useCallback(
    async (action: string) => {
      if (!gameState || !action.trim() || isBusy || gameState.game_over) return;

      const trimmedAction = action.trim();
      setInputValue("");
      setIsLoading(true);

      addFeedItems([
        {
          id: nextFeedId(),
          type: "player",
          text: formatPlayerAction(trimmedAction, gameState),
        },
      ]);

      try {
        // Use streaming endpoint — content appears piece by piece like live theater
        await submitTurnStream(
          gameState.session_id,
          trimmedAction,
          (event) => {
            switch (event.type) {
              case "narration":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "system", text: event.text }]);
                }
                break;
              case "narration_update":
                // Replace the most recent system/narration entry
                if (event.text) {
                  const updateText = event.text as string;
                  setFeedItems((prev) => {
                    const idx = prev.findLastIndex((item) => item.type === "system");
                    if (idx >= 0) {
                      const updated = [...prev];
                      updated[idx] = { ...updated[idx], text: updateText };
                      return updated;
                    }
                    return [...prev, { id: nextFeedId(), type: "system" as const, text: updateText }];
                  });
                }
                break;
              case "director":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "director", text: event.text }]);
                }
                break;
              case "npc":
                if (event.text) {
                  addFeedItems([{
                    id: nextFeedId(),
                    type: "npc",
                    text: event.text,
                    character: event.character,
                  }]);
                  // Speak this character's line immediately
                  if (voicePlaybackEnabled && voiceStatus?.tts.available && event.voice) {
                    synthesizeSpeech(event.text, event.voice, event.speed).then((speech) => {
                      const audio = new Audio();
                      // Set handlers BEFORE assigning src to avoid race condition
                      audio.oncanplaythrough = () => audio.play().catch(() => {});
                      audio.onerror = () => { audio.src = ""; };
                      audio.src = `data:${speech.mime_type};base64,${speech.audio_base64}`;
                    }).catch(() => {});
                  }
                }
                break;
              case "ambient_hint":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "event", text: event.text }]);
                }
                break;
              case "event":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "event", text: event.text }]);
                }
                break;
              case "clue":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "clue", text: event.text }]);
                }
                break;
              case "scene_image":
                if (event.url) {
                  addFeedItems([{
                    id: nextFeedId(),
                    type: "scene_image",
                    text: event.scene || "",
                    imageUrl: event.url,
                  }]);
                }
                break;
              case "ending":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "ending", text: event.text }]);
                }
                break;
              case "truth_hint":
                if (event.text) {
                  addFeedItems([{
                    id: nextFeedId(), type: "truth_hint", text: event.text,
                    intensity: event.intensity,
                  }]);
                }
                break;
              case "dramatic_event":
                if (event.text) {
                  addFeedItems([{
                    id: nextFeedId(), type: "dramatic_event", text: event.text,
                    character: event.character, characterId: event.character_id,
                    mood: event.mood,
                  }]);
                }
                break;
              case "truth_replay":
                if (event.text) {
                  addFeedItems([{
                    id: nextFeedId(), type: "truth_replay", text: event.text,
                    step: event.step, totalSteps: event.total,
                  }]);
                }
                break;
              case "afterword":
                if (event.text) {
                  addFeedItems([{
                    id: nextFeedId(), type: "afterword", text: event.text,
                    character: event.character, characterId: event.character_id,
                  }]);
                }
                break;
              case "score_card":
                addFeedItems([{
                  id: nextFeedId(), type: "score_card",
                  text: event.summary || "",
                  totalScore: event.total_score,
                  rank: event.rank,
                  rankTitle: event.rank_title,
                  clueScore: event.clue_score,
                  deductionScore: event.deduction_score,
                  efficiencyScore: event.efficiency_score,
                  interactionScore: event.interaction_score,
                }]);
                break;
              case "checkpoint":
                if (event.prompt) {
                  addFeedItems([{
                    id: nextFeedId(), type: "checkpoint",
                    text: event.prompt,
                    prompt: event.prompt,
                    options: event.options,
                  }]);
                }
                break;
              case "checkpoint_feedback":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "director", text: event.text }]);
                }
                break;
              case "confrontation":
                if (event.prompt) {
                  addFeedItems([{
                    id: nextFeedId(), type: "confrontation",
                    text: event.prompt,
                    prompt: event.prompt,
                    character: event.character,
                    characterId: event.character_id,
                    evidenceText: event.evidence_text,
                    options: event.options,
                  }]);
                }
                break;
              case "confrontation_result":
                if (event.text) {
                  addFeedItems([{
                    id: nextFeedId(), type: "npc", text: event.text,
                    character: event.character,
                  }]);
                }
                break;
              case "action_blocked":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "action_blocked", text: event.text }]);
                }
                break;
              case "clue_discovery":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "clue", text: event.text }]);
                }
                break;
              case "lie_caught":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "event", text: event.text }]);
                }
                break;
              case "npc_action":
                if (event.text) {
                  addFeedItems([{ id: nextFeedId(), type: "event", text: event.text }]);
                }
                break;
              case "state":
                // Update game state from streamed data
                if (event.game_state && typeof event.game_state === "object" && "session_id" in (event.game_state as unknown as Record<string, unknown>)) {
                  setGameState(event.game_state as GameState);
                } else if (event.game_state) {
                  setGameState(event.game_state as GameState);
                } else {
                  setGameState((prev) =>
                    prev ? {
                      ...prev,
                      round: event.round ?? prev.round,
                      phase: event.phase ?? prev.phase,
                      tension: event.tension ?? prev.tension,
                      scene: event.scene ?? prev.scene,
                      game_over: event.game_over ?? prev.game_over,
                    } : prev
                  );
                }
                // Update ambient audio for scene/tension changes
                if (event.scene || event.tension !== undefined) {
                  if (!ambientRef.current) {
                    ambientRef.current = new AmbientAudioManager();
                  }
                  ambientRef.current.switchScene(
                    event.scene || gameState?.scene || "宴会厅",
                    event.tension ?? gameState?.tension ?? 20,
                  );
                }
                break;
              case "error":
                addFeedItems([{ id: nextFeedId(), type: "system", text: `错误: ${event.text}` }]);
                break;
            }
          },
        );
      } catch (err) {
        // Fallback to non-streaming if SSE fails
        try {
          const turnResult = await submitTurn(gameState.session_id, trimmedAction);
          applyTurnResult(turnResult);
          void speakTurn(turnResult);
        } catch (fallbackErr) {
          const errorMessage = fallbackErr instanceof Error ? fallbackErr.message : "未知错误";
          addFeedItems([{ id: nextFeedId(), type: "system", text: `请求失败: ${errorMessage}` }]);
        }
      } finally {
        setIsLoading(false);
        inputRef.current?.focus();
      }
    },
    [addFeedItems, applyTurnResult, gameState, isBusy, speakTurn, voicePlaybackEnabled, voiceStatus]
  );

  const startVoiceRecording = useCallback(async () => {
    if (!canUseVoiceInput) {
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      setVoiceError("当前浏览器不支持麦克风录音。");
      return;
    }

    stopPlayback();
    setVoiceError(null);

    const recorder = new BrowserWavRecorder();
    try {
      await recorder.start();
      recorderRef.current = recorder;
      setIsRecording(true);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "未知错误";
      setVoiceError(`无法启动录音：${errorMessage}`);
      void recorder.dispose();
    }
  }, [canUseVoiceInput, stopPlayback]);

  const stopVoiceRecording = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder || !gameState) {
      return;
    }

    setIsRecording(false);
    setIsVoiceSubmitting(true);
    setIsLoading(true);
    recorderRef.current = null;

    try {
      const recording = await recorder.stop();
      if (recording.durationMs < 350) {
        throw new Error("录音太短，请再说一次。");
      }

      const voiceTurn = await submitVoiceTurn(gameState.session_id, recording.blob);
      if (!voiceTurn.transcript?.trim()) {
        throw new Error("语音识别结果为空，请再试一次。");
      }
      addFeedItems([
        {
          id: nextFeedId(),
          type: "player",
          text: voiceTurn.transcript,
        },
      ]);

      applyTurnResult(voiceTurn.turn);
      void speakTurn(voiceTurn.turn);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "未知错误";
      setVoiceError(`语音提交失败：${errorMessage}`);
      addFeedItems([
        {
          id: nextFeedId(),
          type: "system",
          text: `语音提交失败: ${errorMessage}`,
        },
      ]);
      void recorder.dispose();
    } finally {
      setIsVoiceSubmitting(false);
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [addFeedItems, applyTurnResult, gameState, speakTurn]);

  const handleVoiceToggle = useCallback(() => {
    if (isRecording) {
      void stopVoiceRecording();
      return;
    }
    void startVoiceRecording();
  }, [isRecording, startVoiceRecording, stopVoiceRecording]);

  const handleInputSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      handleSubmitAction(inputValue);
    },
    [handleSubmitAction, inputValue]
  );

  const handleReset = useCallback(() => {
    if (recorderRef.current) {
      void recorderRef.current.dispose();
      recorderRef.current = null;
      setIsRecording(false);
    }
    initializeGame();
  }, [initializeGame]);

  const handleUndo = useCallback(async () => {
    if (!gameState || isBusy) return;
    try {
      const res = await fetch(`${API_URL}/api/undo/${gameState.session_id}`, { method: "POST" });
      if (!res.ok) return;
      const data = await res.json();
      // Restore game state from server
      if (data.game_state) {
        setGameState(data.game_state);
      }
      // Remove feed items from the last player action onwards
      setFeedItems((prev) => {
        const lastPlayerIdx = prev.findLastIndex((item) => item.type === "player");
        if (lastPlayerIdx < 0) return prev;
        return prev.slice(0, lastPlayerIdx);
      });
    } catch { /* ignore */ }
  }, [gameState, isBusy]);

  const handleQuickAction = useCallback(
    (action: string) => {
      handleSubmitAction(action);
    },
    [handleSubmitAction]
  );

  return (
    <div className={`h-screen flex flex-col overflow-hidden tension-bg ${
      (gameState?.tension || 0) < 35 ? "tension-low" :
      (gameState?.tension || 0) < 65 ? "tension-mid" : "tension-high"
    }`}>
      <div className="shrink-0 p-3">
        <GameBoard
          title={gameState?.title || "Unscripted | 非剧本杀"}
          scene={gameState?.scene || "..."}
          phase={gameState?.phase || "..."}
          round={gameState?.round || 0}
          maxRounds={gameState?.max_rounds || 20}
          cluesFound={gameState?.clues?.filter((c) => c.discovered).length || 0}
          totalClues={gameState?.clues?.length || 0}
          tension={gameState?.tension || 0}
          actionPoints={gameState?.action_points ?? 2}
          maxActionPoints={gameState?.max_action_points ?? 2}
          onReset={handleReset}
          isLoading={isBusy}
        />
      </div>

      <div className="flex-1 flex overflow-hidden px-3 pb-3 gap-3">
        <div className="flex-1 flex flex-col min-w-0 bg-slate-800/40 border border-slate-700/50 rounded-lg overflow-hidden">
          <StoryFeed items={feedItems} isLoading={isBusy} />

          <div className="shrink-0 border-t border-slate-700/50">
            {gameState?.game_over ? (
              <div className="p-4 text-center">
                <p className="text-amber-400 text-sm mb-3">游戏结束</p>
                <div className="flex items-center justify-center gap-3">
                  <button
                    onClick={async () => {
                      try {
                        const res = await fetch(`${API_URL}/api/report/${gameState.session_id}`);
                        if (res.ok) {
                          const data = await res.json();
                          setCaseReportData(data);
                        }
                      } catch { /* ignore */ }
                    }}
                    className="btn-transition px-6 py-2 bg-slate-700 hover:bg-slate-600 text-amber-300 rounded-lg text-sm font-medium border border-amber-700/40"
                  >
                    查看侦探档案
                  </button>
                  <button
                    onClick={handleReset}
                    className="btn-transition px-6 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium"
                  >
                    重新开始
                  </button>
                </div>
              </div>
            ) : (
              <>
                <div className="px-4 pt-4 pb-1">
                  {isAwaitingCheckpoint ? (
                    <div className="rounded-lg border border-indigo-700/40 bg-indigo-950/20 p-3">
                      <p className="text-sm text-indigo-100 font-medium">
                        {checkpointState?.prompt || "选择你的假说："}
                      </p>
                      <div className="mt-3 flex flex-col gap-2">
                        {checkpointState?.options.map((option) => (
                          <button
                            key={option.id}
                            onClick={() => handleSubmitAction(option.id)}
                            disabled={isBusy}
                            className="btn-transition rounded-lg border border-indigo-600/50 px-4 py-2.5 text-sm text-indigo-200 hover:bg-indigo-900/30 text-left disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : isAwaitingConfrontation ? (
                    <div className="rounded-lg border border-red-700/40 bg-red-950/20 p-3">
                      <p className="text-sm text-red-100 font-medium">
                        {confrontationState?.prompt || "选择你的追问方式："}
                      </p>
                      {confrontationState?.evidence_text && (
                        <p className="text-xs text-amber-300/60 mt-1 italic">
                          证据: {confrontationState.evidence_text}
                        </p>
                      )}
                      <div className="mt-3 flex flex-col gap-2">
                        {confrontationState?.options.map((option) => (
                          <button
                            key={option.id}
                            onClick={() => handleSubmitAction(option.id)}
                            disabled={isBusy}
                            className="btn-transition rounded-lg border border-red-600/50 px-4 py-2.5 text-sm text-red-200 hover:bg-red-900/30 text-left disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : isAwaitingVote ? (
                    <div className="rounded-lg border border-amber-700/40 bg-amber-950/20 p-3">
                      <p className="text-sm text-amber-100">
                        {voteState?.prompt || "公开对峙已经开始，给出你的最终判断。"}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {voteState?.options.map((option) => (
                          <button
                            key={option.id}
                            onClick={() => handleSubmitAction(`投票:${option.id}`)}
                            disabled={isBusy}
                            className="btn-transition rounded-lg border border-amber-600/50 px-3 py-2 text-sm text-amber-200 hover:bg-amber-900/30 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            投票给 {option.label}
                          </button>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="px-4 pb-2 pt-3">
                  <div className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-700/50 bg-slate-900/50 px-3 py-2 text-xs text-slate-300">
                    <button
                      type="button"
                      onClick={handleVoiceToggle}
                      disabled={!canUseVoiceInput && !isRecording}
                      className={`btn-transition inline-flex items-center gap-2 rounded-lg border px-3 py-2 text-sm ${
                        isRecording
                          ? "recording-ring border-rose-500/60 bg-rose-950/30 text-rose-100"
                          : "border-cyan-700/40 bg-cyan-950/20 text-cyan-100 disabled:cursor-not-allowed disabled:opacity-50"
                      }`}
                    >
                      <span className="inline-block h-2.5 w-2.5 rounded-full bg-current" />
                      {isRecording ? "结束录音并发送" : "语音输入"}
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        stopPlayback();
                        setVoicePlaybackEnabled((prev) => !prev);
                      }}
                      className={`btn-transition rounded-lg border px-3 py-2 ${
                        voicePlaybackEnabled
                          ? "border-amber-700/40 bg-amber-950/20 text-amber-100"
                          : "border-slate-700/50 bg-slate-800/60 text-slate-400"
                      }`}
                    >
                      {voicePlaybackEnabled ? "播报开启" : "播报关闭"}
                    </button>

                    <span className="rounded-full border border-slate-700/60 px-2 py-1 text-[11px] text-slate-400">
                      ASR: {voiceStatus?.asr.available ? `${voiceStatus.asr.provider}/${voiceStatus.asr.model}` : "不可用"}
                    </span>
                    <span className="rounded-full border border-slate-700/60 px-2 py-1 text-[11px] text-slate-400">
                      播报: {voiceStatus?.tts.available ? `${voiceStatus.tts.provider}/${voiceStatus.tts.model}` : "浏览器 fallback"}
                    </span>

                    {voiceError ? (
                      <span className="text-[11px] text-rose-300">{voiceError}</span>
                    ) : isRecording ? (
                      <span className="text-[11px] text-rose-200">录音中，再点一次结束</span>
                    ) : (
                      <span className="text-[11px] text-slate-500">
                        半实时语音链：ASR -&gt; 文本回合 -&gt; 播报
                      </span>
                    )}
                  </div>
                </div>

                <form onSubmit={handleInputSubmit} className="p-3 flex gap-2">
                  <button
                    type="button"
                    onClick={handleUndo}
                    disabled={isBusy || feedItems.findLastIndex((i) => i.type === "player") < 0}
                    className="btn-transition shrink-0 px-3 py-2.5 bg-slate-700 hover:bg-slate-600 disabled:bg-slate-800 disabled:text-slate-600 text-slate-300 rounded-lg text-sm disabled:cursor-not-allowed"
                    title="撤回上一条"
                  >
                    撤回
                  </button>
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder={
                      isInteractiveBlocked
                        ? "请选择上方的选项"
                        : isRecording
                          ? "录音中..."
                          : "输入你的行动..."
                    }
                    disabled={isBusy || !gameState || isInteractiveBlocked || isRecording}
                    className="flex-1 bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 disabled:opacity-50 disabled:cursor-not-allowed focus:border-amber-600/50"
                  />
                  <button
                    type="submit"
                    disabled={
                      isBusy || !inputValue.trim() || !gameState || isInteractiveBlocked || isRecording
                    }
                    className="btn-transition shrink-0 px-5 py-2.5 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg text-sm font-medium disabled:cursor-not-allowed"
                  >
                    {isBusy ? (
                      <span className="inline-flex items-center gap-1.5">
                        <span className="pulse-glow inline-block w-1 h-1 bg-white rounded-full" />
                        <span className="pulse-glow inline-block w-1 h-1 bg-white rounded-full" style={{ animationDelay: "200ms" }} />
                        <span className="pulse-glow inline-block w-1 h-1 bg-white rounded-full" style={{ animationDelay: "400ms" }} />
                      </span>
                    ) : (
                      "发送"
                    )}
                  </button>
                </form>

                {!isInteractiveBlocked && (
                  <QuickActions
                    onAction={handleQuickAction}
                    disabled={isBusy || !gameState || isRecording}
                    scene={gameState?.scene || ""}
                    characters={gameState?.characters || []}
                    clues={gameState?.clues || []}
                    round={gameState?.round || 0}
                    tension={gameState?.tension || 0}
                  />
                )}
              </>
            )}
          </div>
        </div>

        <div className="hidden lg:flex w-80 shrink-0 flex-col gap-3 overflow-y-auto">
          <LocationMap
            characters={gameState?.characters || []}
            playerScene={gameState?.scene || "宴会厅"}
          />
          <DetectiveNotebook
            characters={gameState?.characters || []}
            clues={gameState?.clues || []}
            events={gameState?.events || []}
            round={gameState?.round || 0}
            scene={gameState?.scene || ""}
          />
          <CharacterPanel characters={charactersWithPortraits} />
          <CluePanel clues={gameState?.clues || []} />
          <WorldLedger events={gameState?.events || []} />
        </div>

        <div className="flex lg:hidden w-72 shrink-0 flex-col overflow-hidden bg-slate-800/40 border border-slate-700/50 rounded-lg">
          <div className="shrink-0 flex border-b border-slate-700/50">
            <button
              onClick={() => setSidebarTab("characters")}
              className={`flex-1 py-2 text-xs font-medium btn-transition ${
                sidebarTab === "characters"
                  ? "text-amber-400 border-b-2 border-amber-400"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              角色
            </button>
            <button
              onClick={() => setSidebarTab("info")}
              className={`flex-1 py-2 text-xs font-medium btn-transition ${
                sidebarTab === "info"
                  ? "text-amber-400 border-b-2 border-amber-400"
                  : "text-slate-500 hover:text-slate-300"
              }`}
            >
              线索 & 事件
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            {sidebarTab === "characters" ? (
              <CharacterPanel characters={charactersWithPortraits} />
            ) : (
              <div className="space-y-4">
                <DetectiveNotebook
                  characters={gameState?.characters || []}
                  clues={gameState?.clues || []}
                  events={gameState?.events || []}
                  round={gameState?.round || 0}
                  scene={gameState?.scene || ""}
                />
                <CluePanel clues={gameState?.clues || []} />
                <WorldLedger events={gameState?.events || []} />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Case Report Modal */}
      {caseReportData && (
        <CaseReport
          data={caseReportData}
          onClose={() => setCaseReportData(null)}
        />
      )}
    </div>
  );
}
