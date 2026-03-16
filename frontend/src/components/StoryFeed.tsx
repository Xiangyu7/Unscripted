"use client";

import React, { useEffect, useRef } from "react";
import { FeedItem } from "@/lib/types";

interface StoryFeedProps {
  items: FeedItem[];
  isLoading: boolean;
}

function ScoreBar({ label, score, max, color }: { label: string; score: number; max: number; color: string }) {
  const pct = Math.round((score / max) * 100);
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-16 text-right text-slate-400">{label}</span>
      <div className="flex-1 h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-1000 ease-out`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-10 text-slate-300">{score}/{max}</span>
    </div>
  );
}

function FeedItemCard({ item }: { item: FeedItem }) {
  const baseClasses =
    "feed-item-enter rounded-lg px-4 py-3 mb-3 border text-sm leading-relaxed";

  switch (item.type) {
    case "system":
      return (
        <div className={`${baseClasses} bg-slate-800/60 border-slate-700/50 text-slate-300`}>
          <span className="inline-block text-xs font-medium text-slate-500 bg-slate-700/50 rounded px-1.5 py-0.5 mb-1.5">
            系统
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "director":
      return (
        <div className={`${baseClasses} bg-violet-950/30 border-violet-800/40 text-violet-200`}>
          <span className="inline-block text-xs font-medium text-violet-400 bg-violet-900/40 rounded px-1.5 py-0.5 mb-1.5">
            导演
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "player":
      return (
        <div className={`${baseClasses} bg-blue-950/30 border-blue-800/40 text-blue-200 ml-8`}>
          <span className="inline-block text-xs font-medium text-blue-400 bg-blue-900/40 rounded px-1.5 py-0.5 mb-1.5">
            你
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "npc":
      return (
        <div className={`${baseClasses} bg-slate-700/40 border-slate-600/50 text-slate-200`}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-block text-xs font-medium text-amber-300 bg-amber-900/30 rounded px-1.5 py-0.5">
              {item.character || "NPC"}
            </span>
          </div>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "clue":
      return (
        <div className={`${baseClasses} clue-glow bg-amber-950/20 border-amber-700/40 text-amber-200`}>
          <div className="flex items-center gap-2 mb-1.5">
            <svg
              className="w-4 h-4 text-amber-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <span className="inline-block text-xs font-medium text-amber-400 bg-amber-900/30 rounded px-1.5 py-0.5">
              线索
            </span>
          </div>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "event": {
      const isLieCaught = item.text.includes("你说你") || item.text.includes("你怎么解释");
      return (
        <div className={`${baseClasses} ${
          isLieCaught
            ? "lie-caught bg-red-950/20 border-red-800/40 text-red-100 not-italic"
            : "bg-slate-800/30 border-slate-700/30 text-slate-400 italic"
        }`}>
          <span className={`inline-block text-xs font-medium rounded px-1.5 py-0.5 mb-1.5 ${
            isLieCaught
              ? "text-red-300 bg-red-900/40"
              : "text-slate-500 bg-slate-700/30"
          }`}>
            {isLieCaught ? "揭穿谎言" : "事件"}
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );
    }

    case "scene_image":
      return (
        <div className={`${baseClasses} bg-slate-900/60 border-slate-600/50 p-0 overflow-hidden`}>
          <div className="relative">
            <img
              src={item.imageUrl}
              alt={item.text}
              className="w-full h-auto rounded-t-lg object-cover max-h-80"
              loading="lazy"
            />
            <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-slate-900/90 to-transparent px-4 py-3">
              <span className="inline-block text-xs font-medium text-cyan-300 bg-cyan-900/40 rounded px-1.5 py-0.5 mb-1">
                场景
              </span>
              <p className="text-slate-200 text-sm">{item.text}</p>
            </div>
          </div>
        </div>
      );

    case "ending":
      return (
        <div className={`${baseClasses} bg-gradient-to-br from-amber-950/30 via-slate-800/60 to-violet-950/30 border-amber-600/50 text-amber-100`}>
          <div className="text-center">
            <span className="inline-block text-sm font-bold text-amber-400 bg-amber-900/30 rounded px-3 py-1 mb-3">
              -- 游戏结束 --
            </span>
            <p className="whitespace-pre-wrap text-base leading-relaxed">
              {item.text}
            </p>
          </div>
        </div>
      );

    // ═══ New event types ═══

    case "truth_hint":
      return (
        <div className={`${baseClasses} ${
          item.intensity === "strong"
            ? "truth-hint-strong bg-purple-950/30 border-purple-600/50 text-purple-200"
            : "bg-purple-950/20 border-purple-800/30 text-purple-300/80"
        }`}>
          <div className="flex items-center gap-2">
            <span className="inline-block w-2 h-2 rounded-full bg-purple-400 pulse-glow" />
            <p className="whitespace-pre-wrap italic">{item.text}</p>
          </div>
        </div>
      );

    case "dramatic_event":
      return (
        <div className={`${baseClasses} bg-slate-900/80 border-2 border-amber-700/60 text-slate-100 dramatic-enter`}>
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-block text-xs font-bold text-amber-400 bg-amber-900/40 rounded px-2 py-0.5 tracking-wider">
              {item.character}
            </span>
            {item.mood && (
              <span className="text-xs text-slate-500">{item.mood}</span>
            )}
          </div>
          <p className="whitespace-pre-wrap text-base leading-relaxed font-medium">
            {item.text}
          </p>
        </div>
      );

    case "truth_replay":
      return (
        <div className={`${baseClasses} bg-red-950/15 border-red-900/30 text-red-200/90`}>
          <div className="flex items-start gap-3">
            <div className="flex flex-col items-center">
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-red-900/50 text-red-300 text-xs font-bold border border-red-700/40">
                {item.step}
              </span>
              {item.step !== item.totalSteps && (
                <div className="w-px h-4 bg-red-800/30 mt-1" />
              )}
            </div>
            <p className="whitespace-pre-wrap flex-1 pt-0.5">{item.text}</p>
          </div>
        </div>
      );

    case "afterword":
      return (
        <div className={`${baseClasses} bg-slate-800/40 border-slate-600/40 text-slate-200`}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-block text-xs font-medium text-cyan-300 bg-cyan-900/30 rounded px-1.5 py-0.5">
              {item.character} · 真心话
            </span>
          </div>
          <p className="whitespace-pre-wrap italic">{item.text}</p>
        </div>
      );

    case "score_card":
      return (
        <div className={`${baseClasses} bg-gradient-to-br from-slate-800/80 via-slate-800/60 to-amber-950/30 border-amber-700/40 text-slate-200`}>
          <div className="text-center mb-3">
            <span className="inline-block text-lg font-bold text-amber-400">
              {item.rankTitle}
            </span>
            <div className="text-3xl font-bold text-amber-300 mt-1">
              {item.totalScore}<span className="text-base text-slate-400">/100</span>
            </div>
            <span className="inline-block text-xs text-amber-500/80 bg-amber-900/20 rounded-full px-3 py-0.5 mt-1">
              {item.rank}级
            </span>
          </div>
          <div className="space-y-2 mt-3">
            <ScoreBar label="线索收集" score={item.clueScore ?? 0} max={40} color="bg-amber-500" />
            <ScoreBar label="推理质量" score={item.deductionScore ?? 0} max={30} color="bg-violet-500" />
            <ScoreBar label="调查效率" score={item.efficiencyScore ?? 0} max={15} color="bg-emerald-500" />
            <ScoreBar label="审讯互动" score={item.interactionScore ?? 0} max={15} color="bg-cyan-500" />
          </div>
          {item.text && (
            <p className="whitespace-pre-wrap text-xs text-slate-400 mt-3 text-center">{item.text}</p>
          )}
        </div>
      );

    case "checkpoint":
      return (
        <div className={`${baseClasses} bg-indigo-950/30 border-indigo-700/40 text-indigo-200`}>
          <span className="inline-block text-xs font-bold text-indigo-400 bg-indigo-900/40 rounded px-2 py-0.5 mb-2">
            推理检查点
          </span>
          <p className="whitespace-pre-wrap font-medium">{item.prompt || item.text}</p>
        </div>
      );

    case "confrontation":
      return (
        <div className={`${baseClasses} bg-red-950/20 border-red-800/40 text-red-100`}>
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-block text-xs font-bold text-red-400 bg-red-900/40 rounded px-2 py-0.5">
              证据对质 · {item.character}
            </span>
          </div>
          {item.evidenceText && (
            <p className="text-xs text-amber-300/70 mb-2 italic">证据: {item.evidenceText}</p>
          )}
          <p className="whitespace-pre-wrap font-medium">{item.prompt || item.text}</p>
        </div>
      );

    case "action_blocked":
      return (
        <div className={`${baseClasses} bg-slate-800/40 border-slate-600/40 text-slate-400`}>
          <span className="inline-block text-xs font-medium text-slate-500 bg-slate-700/40 rounded px-1.5 py-0.5 mb-1.5">
            行动受限
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    default:
      return (
        <div className={`${baseClasses} bg-slate-800 border-slate-700 text-slate-300`}>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );
  }
}

export default function StoryFeed({ items, isLoading }: StoryFeedProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [items, isLoading]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto p-4 space-y-1"
    >
      {items.length === 0 && !isLoading && (
        <div className="flex items-center justify-center h-full text-slate-500 text-sm">
          正在准备故事...
        </div>
      )}

      {items.map((item) => (
        <FeedItemCard key={item.id} item={item} />
      ))}

      {isLoading && (
        <div className="feed-item-enter flex items-center gap-2 px-4 py-3 text-sm text-slate-400">
          <div className="flex gap-1">
            <span className="pulse-glow inline-block w-1.5 h-1.5 bg-amber-400 rounded-full" style={{ animationDelay: "0ms" }} />
            <span className="pulse-glow inline-block w-1.5 h-1.5 bg-amber-400 rounded-full" style={{ animationDelay: "300ms" }} />
            <span className="pulse-glow inline-block w-1.5 h-1.5 bg-amber-400 rounded-full" style={{ animationDelay: "600ms" }} />
          </div>
          <span>思考中...</span>
        </div>
      )}
    </div>
  );
}
