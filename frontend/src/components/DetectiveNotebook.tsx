"use client";

import React, { useMemo } from "react";
import { Character, Clue, GameEvent } from "@/lib/types";

interface DetectiveNotebookProps {
  characters: Character[];
  clues: Clue[];
  events: GameEvent[];
  round: number;
  scene: string;
}

function RecentRecap({ events, round }: { events: GameEvent[]; round: number }) {
  // Show last 5 rounds of key events
  const recentEvents = useMemo(() => {
    const startRound = Math.max(1, round - 4);
    return events
      .filter(
        (e) =>
          e.round >= startRound &&
          e.type !== "npc_event" &&
          e.type !== "npc_share"
      )
      .slice(-8);
  }, [events, round]);

  if (recentEvents.length === 0) return null;

  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
        最近动态
      </h3>
      <div className="space-y-1 max-h-32 overflow-y-auto">
        {recentEvents.map((evt, i) => (
          <div key={i} className="flex items-start gap-1.5 text-xs">
            <span className="shrink-0 text-slate-600 font-mono w-4 text-right">
              {evt.round}
            </span>
            <span className="text-slate-400 leading-snug line-clamp-2">
              {evt.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ClueConnections({ clues }: { clues: Clue[] }) {
  const discovered = clues.filter((c) => c.discovered);
  if (discovered.length < 2) return null;

  // Auto-generate deduction hints based on discovered clues
  const deductions: string[] = [];

  const hasStudyScratches = discovered.some((c) => c.id === "study_scratches");
  const hasCellarFootprint = discovered.some((c) => c.id === "wine_cellar_footprint");
  const hasTornLetter = discovered.some((c) => c.id === "torn_letter");
  const hasWillDraft = discovered.some((c) => c.id === "will_draft");
  const hasAnonymousTip = discovered.some((c) => c.id === "anonymous_tip");
  const hasCellarSound = discovered.some((c) => c.id === "cellar_sound");
  const hasCellarProvisions = discovered.some((c) => c.id === "cellar_provisions");
  const hasPhoneLog = discovered.some((c) => c.id === "linlan_phone_log");
  const hasStagedEvidence = discovered.some((c) => c.id === "staged_evidence");

  if (hasStudyScratches && hasCellarFootprint) {
    deductions.push("有人从书房出去后直接去了酒窖——同一个人？");
  }
  if (hasTornLetter && hasAnonymousTip) {
    deductions.push("撕碎的信提到'计划'，纸条提前预告了今晚——有人策划了这一切");
  }
  if (hasWillDraft) {
    deductions.push("遗嘱便签上写着'看看他们的反应'——这是一场测试？");
  }
  if (hasCellarProvisions && hasCellarFootprint) {
    deductions.push("酒窖有食物和毛毯，脚印只进不出——有人自愿待在那里");
  }
  if (hasCellarSound && hasCellarProvisions) {
    deductions.push("酒窖有呼吸声+生活物资——顾言可能还活着，就藏在酒窖里！");
  }
  if (hasPhoneLog) {
    deductions.push("顾言'失踪后'还在给林岚发消息——他根本没有遇险，林岚是共犯");
  }
  if (hasStagedEvidence) {
    deductions.push("失踪现场是伪造的——整件事是一场自导自演");
  }
  if (hasPhoneLog && hasCellarSound && hasWillDraft) {
    deductions.push("真相浮现：顾言用修改遗嘱作为诱饵，假装失踪来试探所有人的真面目！");
  }

  if (deductions.length === 0) return null;

  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold text-amber-400 uppercase tracking-wider">
        推理线索
      </h3>
      <div className="space-y-1">
        {deductions.map((d, i) => (
          <div
            key={i}
            className="text-xs text-amber-200/80 bg-amber-950/20 border border-amber-800/20 rounded px-2 py-1.5 leading-snug"
          >
            {d}
          </div>
        ))}
      </div>
    </div>
  );
}

function CharacterTracker({ characters, scene }: { characters: Character[]; scene: string }) {
  const shortScene = ["宴会厅", "书房", "花园", "酒窖", "走廊"].find((s) => scene.includes(s)) || scene;

  return (
    <div className="space-y-1">
      <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
        人物位置
      </h3>
      <div className="grid grid-cols-1 gap-1">
        {characters.map((c) => {
          const isHere = c.location === shortScene || scene.includes(c.location);
          return (
            <div
              key={c.id}
              className={`flex items-center justify-between text-xs px-2 py-1 rounded ${
                isHere
                  ? "bg-cyan-950/30 border border-cyan-800/30 text-cyan-200"
                  : "bg-slate-800/50 text-slate-500"
              }`}
            >
              <span className="font-medium">{c.name}</span>
              <span className={isHere ? "text-cyan-400" : "text-slate-600"}>
                {isHere ? "在这里" : c.location}
              </span>
            </div>
          );
        })}
        <div className="flex items-center justify-between text-xs px-2 py-1 rounded bg-blue-950/30 border border-blue-800/30 text-blue-200">
          <span className="font-medium">你</span>
          <span className="text-blue-400">{shortScene}</span>
        </div>
      </div>
    </div>
  );
}

export default function DetectiveNotebook({
  characters,
  clues,
  events,
  round,
  scene,
}: DetectiveNotebookProps) {
  const discovered = clues.filter((c) => c.discovered);

  return (
    <div className="space-y-3">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider px-1">
        侦探笔记
      </h2>

      <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-3">
        {/* Character location tracker */}
        <CharacterTracker characters={characters} scene={scene} />

        {/* Clue connections / deductions */}
        <ClueConnections clues={clues} />

        {/* Recent recap */}
        <RecentRecap events={events} round={round} />

        {/* Hint when no clues */}
        {discovered.length === 0 && (
          <p className="text-xs text-slate-500 italic">
            还没有发现线索。试试搜查各个房间，或者观察嫌疑人的行为。
          </p>
        )}
      </div>
    </div>
  );
}
