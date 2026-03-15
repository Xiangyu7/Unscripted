"use client";

import React, { useEffect, useRef } from "react";
import { FeedItem } from "@/lib/types";

interface StoryFeedProps {
  items: FeedItem[];
  isLoading: boolean;
}

const typeLabels: Record<FeedItem["type"], string> = {
  system: "系统",
  director: "导演",
  player: "你",
  npc: "NPC",
  clue: "线索",
  event: "事件",
  ending: "结局",
  scene_image: "场景",
};

function FeedItemCard({ item }: { item: FeedItem }) {
  const baseClasses =
    "feed-item-enter rounded-lg px-4 py-3 mb-3 border text-sm leading-relaxed";

  switch (item.type) {
    case "system":
      return (
        <div className={`${baseClasses} bg-slate-800/60 border-slate-700/50 text-slate-300`}>
          <span className="inline-block text-xs font-medium text-slate-500 bg-slate-700/50 rounded px-1.5 py-0.5 mb-1.5">
            {typeLabels.system}
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "director":
      return (
        <div className={`${baseClasses} bg-violet-950/30 border-violet-800/40 text-violet-200`}>
          <span className="inline-block text-xs font-medium text-violet-400 bg-violet-900/40 rounded px-1.5 py-0.5 mb-1.5">
            {typeLabels.director}
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "player":
      return (
        <div className={`${baseClasses} bg-blue-950/30 border-blue-800/40 text-blue-200 ml-8`}>
          <span className="inline-block text-xs font-medium text-blue-400 bg-blue-900/40 rounded px-1.5 py-0.5 mb-1.5">
            {typeLabels.player}
          </span>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "npc":
      return (
        <div className={`${baseClasses} bg-slate-700/40 border-slate-600/50 text-slate-200`}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className="inline-block text-xs font-medium text-amber-300 bg-amber-900/30 rounded px-1.5 py-0.5">
              {item.character || typeLabels.npc}
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
              {typeLabels.clue}
            </span>
          </div>
          <p className="whitespace-pre-wrap">{item.text}</p>
        </div>
      );

    case "event": {
      // Dramatic styling for caught lies
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
            {isLieCaught ? "揭穿谎言" : typeLabels.event}
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
                {typeLabels.scene_image}
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
