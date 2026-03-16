"use client";

import React from "react";
import { GameEvent } from "@/lib/types";

interface WorldLedgerProps {
  events: GameEvent[];
}

export default function WorldLedger({ events }: WorldLedgerProps) {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider px-1">
        事件记录
      </h2>

      {events.length === 0 ? (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <p className="text-xs text-slate-500">暂无事件记录。</p>
        </div>
      ) : (
        <div className="bg-slate-800 border border-slate-700 rounded-lg overflow-hidden">
          <div className="max-h-48 overflow-y-auto p-2 space-y-1.5">
            {events.map((event, index) => (
              <div
                key={`${event.round}-${event.type}-${index}`}
                className="flex items-start gap-2 text-xs"
              >
                <span className="shrink-0 inline-flex items-center justify-center w-5 h-5 rounded bg-slate-700 text-slate-400 font-mono text-[10px]">
                  {event.round}
                </span>
                <span className="text-slate-400 leading-relaxed">
                  {event.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
