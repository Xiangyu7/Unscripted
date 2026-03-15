"use client";

import React from "react";

interface GameBoardProps {
  title: string;
  scene: string;
  phase: string;
  round: number;
  maxRounds: number;
  tension: number;
  cluesFound: number;
  totalClues: number;
  onReset: () => void;
  isLoading: boolean;
}

export default function GameBoard({
  title,
  scene,
  phase,
  round,
  maxRounds,
  tension,
  cluesFound,
  totalClues,
  onReset,
  isLoading,
}: GameBoardProps) {
  const tensionColor =
    tension < 35
      ? "bg-emerald-500"
      : tension < 65
        ? "bg-yellow-500"
        : "bg-red-500";

  const tensionTextColor =
    tension < 35
      ? "text-emerald-400"
      : tension < 65
        ? "text-yellow-400"
        : "text-red-400";

  const roundsLeft = maxRounds - round;
  const timeUrgency =
    roundsLeft <= 3
      ? "text-red-400"
      : roundsLeft <= 6
        ? "text-yellow-400"
        : "text-slate-200";

  const progressPct = totalClues > 0 ? Math.round((cluesFound / totalClues) * 100) : 0;

  return (
    <header className="bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
      {/* Left: Title and info */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 flex-1 min-w-0">
        <h1 className="text-lg font-bold text-amber-400 whitespace-nowrap">
          {title || "Unscripted"}
        </h1>

        <div className="flex items-center gap-3 text-sm text-slate-400 flex-wrap">
          <span className="inline-flex items-center gap-1">
            <span className="text-slate-500">场景</span>
            <span className="text-slate-200 truncate max-w-[150px]">
              {scene}
            </span>
          </span>

          <span className="hidden sm:inline text-slate-600">|</span>

          <span className="inline-flex items-center gap-1">
            <span className="text-slate-500">阶段</span>
            <span className="text-violet-400">{phase}</span>
          </span>

          <span className="hidden sm:inline text-slate-600">|</span>

          <span className={`inline-flex items-center gap-1 ${timeUrgency}`}>
            <span>
              第{round}轮
            </span>
            <span className="text-slate-500">/ {maxRounds}</span>
            {roundsLeft <= 5 && (
              <span className="text-xs">(剩{roundsLeft}轮)</span>
            )}
          </span>

          <span className="hidden sm:inline text-slate-600">|</span>

          {/* Clue progress */}
          <span className="inline-flex items-center gap-1.5">
            <span className="text-amber-400 text-xs">
              线索 {cluesFound}/{totalClues}
            </span>
            <div className="w-12 h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-amber-500 transition-all duration-500"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </span>
        </div>
      </div>

      {/* Right: Tension + Reset */}
      <div className="flex items-center gap-4 w-full sm:w-auto">
        <div className="flex items-center gap-2 flex-1 sm:flex-none">
          <span className={`text-sm font-medium ${tensionTextColor} whitespace-nowrap`}>
            紧张度 {tension}
          </span>
          <div className="w-24 sm:w-32 h-2.5 bg-slate-700 rounded-full overflow-hidden">
            <div
              className={`tension-bar h-full rounded-full ${tensionColor}`}
              style={{ width: `${Math.min(tension, 100)}%` }}
            />
          </div>
        </div>

        <button
          onClick={onReset}
          disabled={isLoading}
          className="btn-transition px-3 py-1.5 text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 hover:text-white rounded border border-slate-600 hover:border-slate-500 disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
        >
          重新开始
        </button>
      </div>
    </header>
  );
}
