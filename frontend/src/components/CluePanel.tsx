"use client";

import React from "react";
import { Clue } from "@/lib/types";

interface CluePanelProps {
  clues: Clue[];
}

export default function CluePanel({ clues }: CluePanelProps) {
  const discoveredClues = clues.filter((c) => c.discovered);

  return (
    <div className="space-y-2">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider px-1">
        线索
      </h2>

      {discoveredClues.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <p className="text-xs text-slate-500 leading-relaxed">
            暂无线索，先通过观察和试探打开局面。
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {discoveredClues.map((clue) => (
            <div
              key={clue.id}
              className="clue-glow bg-amber-950/15 border border-amber-800/30 rounded-lg p-3"
            >
              <div className="flex items-start gap-2">
                <svg
                  className="w-3.5 h-3.5 text-amber-400 mt-0.5 shrink-0"
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
                <p className="text-xs text-amber-200 leading-relaxed">
                  {clue.text}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
