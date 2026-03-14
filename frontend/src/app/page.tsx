"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { GameState, FeedItem, TurnResponse } from "@/lib/types";
import { resetGame, submitTurn, getState } from "@/lib/api";
import GameBoard from "@/components/GameBoard";
import StoryFeed from "@/components/StoryFeed";
import CharacterPanel from "@/components/CharacterPanel";
import CluePanel from "@/components/CluePanel";
import WorldLedger from "@/components/WorldLedger";
import QuickActions from "@/components/QuickActions";

let feedCounter = 0;
function nextFeedId(): string {
  feedCounter += 1;
  return `feed-${feedCounter}-${Date.now()}`;
}

export default function HomePage() {
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [feedItems, setFeedItems] = useState<FeedItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [sidebarTab, setSidebarTab] = useState<"characters" | "info">("characters");
  const inputRef = useRef<HTMLInputElement>(null);

  const addFeedItems = useCallback((items: FeedItem[]) => {
    setFeedItems((prev) => [...prev, ...items]);
  }, []);

  const initializeGame = useCallback(async () => {
    setIsLoading(true);
    setFeedItems([]);
    feedCounter = 0;

    try {
      const state = await resetGame();
      setGameState(state);

      const initialFeed: FeedItem[] = [];

      // Opening system narration
      initialFeed.push({
        id: nextFeedId(),
        type: "system",
        text: `${state.title}\n\n场景: ${state.scene}`,
      });

      // Show existing events from initial state
      if (state.events && state.events.length > 0) {
        for (const evt of state.events) {
          initialFeed.push({
            id: nextFeedId(),
            type: "event",
            text: evt.text,
          });
        }
      }

      // Public knowledge
      if (state.knowledge?.public_facts && state.knowledge.public_facts.length > 0) {
        initialFeed.push({
          id: nextFeedId(),
          type: "system",
          text: "已知信息:\n" + state.knowledge.public_facts.map((f) => `  - ${f}`).join("\n"),
        });
      }

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
  }, [addFeedItems]);

  useEffect(() => {
    initializeGame();
  }, [initializeGame]);

  const handleSubmitAction = useCallback(
    async (action: string) => {
      if (!gameState || !action.trim() || isLoading || gameState.game_over) return;

      const trimmedAction = action.trim();
      setInputValue("");
      setIsLoading(true);

      // Add player's action to feed
      addFeedItems([
        {
          id: nextFeedId(),
          type: "player",
          text: trimmedAction,
        },
      ]);

      try {
        const turnResult: TurnResponse = await submitTurn(
          gameState.session_id,
          trimmedAction
        );

        const newFeed: FeedItem[] = [];

        // System narration
        if (turnResult.system_narration) {
          newFeed.push({
            id: nextFeedId(),
            type: "system",
            text: turnResult.system_narration,
          });
        }

        // Director note
        if (turnResult.director_note) {
          newFeed.push({
            id: nextFeedId(),
            type: "director",
            text: turnResult.director_note,
          });
        }

        // NPC replies
        if (turnResult.npc_replies) {
          for (const reply of turnResult.npc_replies) {
            newFeed.push({
              id: nextFeedId(),
              type: "npc",
              text: reply.text,
              character: reply.character_name,
            });
          }
        }

        // NPC events
        if (turnResult.npc_events) {
          for (const evt of turnResult.npc_events) {
            newFeed.push({
              id: nextFeedId(),
              type: "event",
              text: evt.text,
            });
          }
        }

        // New clues
        if (turnResult.new_clues && turnResult.new_clues.length > 0) {
          for (const clue of turnResult.new_clues) {
            newFeed.push({
              id: nextFeedId(),
              type: "clue",
              text: clue,
            });
          }
        }

        // Ending
        if (turnResult.game_over && turnResult.ending) {
          newFeed.push({
            id: nextFeedId(),
            type: "ending",
            text: turnResult.ending,
          });
        }

        addFeedItems(newFeed);

        // Refresh full game state
        try {
          const updatedState = await getState(gameState.session_id);
          setGameState(updatedState);
        } catch {
          // If we can't get state, update what we can from turn response
          setGameState((prev) =>
            prev
              ? {
                  ...prev,
                  round: turnResult.round,
                  phase: turnResult.phase,
                  tension: turnResult.tension,
                  scene: turnResult.scene,
                  game_over: turnResult.game_over,
                  ending: turnResult.ending,
                }
              : prev
          );
        }
      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : "未知错误";
        addFeedItems([
          {
            id: nextFeedId(),
            type: "system",
            text: `请求失败: ${errorMessage}`,
          },
        ]);
      } finally {
        setIsLoading(false);
        inputRef.current?.focus();
      }
    },
    [gameState, isLoading, addFeedItems]
  );

  const handleInputSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      handleSubmitAction(inputValue);
    },
    [inputValue, handleSubmitAction]
  );

  const handleReset = useCallback(() => {
    initializeGame();
  }, [initializeGame]);

  const handleQuickAction = useCallback(
    (action: string) => {
      handleSubmitAction(action);
    },
    [handleSubmitAction]
  );

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      {/* Header bar */}
      <div className="shrink-0 p-3">
        <GameBoard
          title={gameState?.title || "Unscripted | 非剧本杀"}
          scene={gameState?.scene || "..."}
          phase={gameState?.phase || "..."}
          round={gameState?.round || 0}
          maxRounds={gameState?.max_rounds || 20}
          tension={gameState?.tension || 0}
          onReset={handleReset}
          isLoading={isLoading}
        />
      </div>

      {/* Main content area */}
      <div className="flex-1 flex overflow-hidden px-3 pb-3 gap-3">
        {/* Left: Story feed + input */}
        <div className="flex-1 flex flex-col min-w-0 bg-slate-800/40 border border-slate-700/50 rounded-lg overflow-hidden">
          {/* Story feed */}
          <StoryFeed items={feedItems} isLoading={isLoading} />

          {/* Input area */}
          <div className="shrink-0 border-t border-slate-700/50">
            {gameState?.game_over ? (
              <div className="p-4 text-center">
                <p className="text-amber-400 text-sm mb-3">
                  游戏结束
                </p>
                <button
                  onClick={handleReset}
                  className="btn-transition px-6 py-2 bg-amber-600 hover:bg-amber-500 text-white rounded-lg text-sm font-medium"
                >
                  重新开始
                </button>
              </div>
            ) : (
              <>
                <form onSubmit={handleInputSubmit} className="p-3 flex gap-2">
                  <input
                    ref={inputRef}
                    type="text"
                    value={inputValue}
                    onChange={(e) => setInputValue(e.target.value)}
                    placeholder="输入你的行动..."
                    disabled={isLoading || !gameState}
                    className="flex-1 bg-slate-900 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-slate-100 placeholder-slate-500 disabled:opacity-50 disabled:cursor-not-allowed focus:border-amber-600/50"
                  />
                  <button
                    type="submit"
                    disabled={isLoading || !inputValue.trim() || !gameState}
                    className="btn-transition shrink-0 px-5 py-2.5 bg-amber-600 hover:bg-amber-500 disabled:bg-slate-700 disabled:text-slate-500 text-white rounded-lg text-sm font-medium disabled:cursor-not-allowed"
                  >
                    {isLoading ? (
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

                <QuickActions
                  onAction={handleQuickAction}
                  disabled={isLoading || !gameState}
                />
              </>
            )}
          </div>
        </div>

        {/* Right: Sidebar - desktop */}
        <div className="hidden lg:flex w-80 shrink-0 flex-col gap-3 overflow-y-auto">
          <CharacterPanel characters={gameState?.characters || []} />
          <CluePanel clues={gameState?.clues || []} />
          <WorldLedger events={gameState?.events || []} />
        </div>

        {/* Right: Sidebar - mobile/tablet (tabbed) */}
        <div className="flex lg:hidden w-72 shrink-0 flex-col overflow-hidden bg-slate-800/40 border border-slate-700/50 rounded-lg">
          {/* Tab headers */}
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

          {/* Tab content */}
          <div className="flex-1 overflow-y-auto p-3">
            {sidebarTab === "characters" ? (
              <CharacterPanel characters={gameState?.characters || []} />
            ) : (
              <div className="space-y-4">
                <CluePanel clues={gameState?.clues || []} />
                <WorldLedger events={gameState?.events || []} />
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
