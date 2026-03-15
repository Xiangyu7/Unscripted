"use client";

import React from "react";
import { Character } from "@/lib/types";

interface CharacterPanelProps {
  characters: Character[];
}

// ── Mood system ──────────────────────────────────────────────────

const MOOD_CONFIG: Record<string, { label: string; color: string; borderColor: string; emoji: string }> = {
  desperate: { label: "绝望", color: "text-red-400", borderColor: "border-red-500 shadow-red-500/30", emoji: "😰" },
  angry:     { label: "愤怒", color: "text-orange-400", borderColor: "border-orange-500 shadow-orange-500/30", emoji: "😠" },
  fearful:   { label: "恐惧", color: "text-purple-400", borderColor: "border-purple-500 shadow-purple-500/30", emoji: "😨" },
  nervous:   { label: "紧张", color: "text-yellow-400", borderColor: "border-yellow-500 shadow-yellow-500/30", emoji: "😟" },
  calm:      { label: "冷静", color: "text-cyan-400", borderColor: "border-cyan-500/50", emoji: "😌" },
  guarded:   { label: "警惕", color: "text-slate-400", borderColor: "border-slate-500", emoji: "🤨" },
  neutral:   { label: "", color: "text-slate-500", borderColor: "border-slate-600", emoji: "" },
};

// ── Character avatar colors ──────────────────────────────────────

const CHAR_COLORS: Record<string, { bg: string; text: string }> = {
  linlan:  { bg: "bg-teal-900/60", text: "text-teal-300" },
  zhoumu:  { bg: "bg-orange-900/60", text: "text-orange-300" },
  songzhi: { bg: "bg-purple-900/60", text: "text-purple-300" },
};

function SuspicionBar({ value }: { value: number }) {
  const color =
    value < 30
      ? "bg-emerald-500"
      : value < 60
        ? "bg-yellow-500"
        : "bg-red-500";

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500 w-10 shrink-0">嫌疑</span>
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
      <span className="text-xs text-slate-400 w-6 text-right">{value}</span>
    </div>
  );
}

function TrustBar({ value }: { value: number }) {
  const normalized = Math.max(0, Math.min(100, value));
  const color =
    value < 30
      ? "bg-red-500"
      : value < 60
        ? "bg-yellow-500"
        : "bg-emerald-500";

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-slate-500 w-10 shrink-0">信任</span>
      <div className="flex-1 h-1.5 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${color} transition-all duration-500`}
          style={{ width: `${normalized}%` }}
        />
      </div>
      <span className="text-xs text-slate-400 w-6 text-right">{value}</span>
    </div>
  );
}

function CharacterAvatar({ character }: { character: Character }) {
  const mood = MOOD_CONFIG[character.mood || "neutral"] || MOOD_CONFIG.neutral;
  const charColor = CHAR_COLORS[character.id] || { bg: "bg-slate-700", text: "text-slate-400" };
  const isIntense = ["desperate", "angry", "fearful"].includes(character.mood || "");

  if (character.portrait_url) {
    return (
      <div className="relative shrink-0">
        <img
          src={character.portrait_url}
          alt={character.name}
          className={`w-12 h-12 rounded-lg object-cover border-2 transition-all duration-500 ${mood.borderColor} ${isIntense ? "shadow-lg" : ""}`}
        />
        {mood.emoji && (
          <span className="absolute -bottom-1 -right-1 text-sm leading-none">
            {mood.emoji}
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="relative shrink-0">
      <div className={`w-12 h-12 rounded-lg border-2 flex items-center justify-center text-lg font-bold transition-all duration-500 ${charColor.bg} ${charColor.text} ${mood.borderColor} ${isIntense ? "shadow-lg" : ""}`}>
        {character.name[0]}
      </div>
      {mood.emoji && (
        <span className="absolute -bottom-1 -right-1 text-sm leading-none">
          {mood.emoji}
        </span>
      )}
    </div>
  );
}

function MoodBadge({ mood }: { mood?: string }) {
  const config = MOOD_CONFIG[mood || "neutral"] || MOOD_CONFIG.neutral;
  if (!config.label) return null;

  return (
    <span className={`text-[10px] ${config.color} bg-slate-800/80 border border-slate-700/50 rounded px-1 py-0.5`}>
      {config.label}
    </span>
  );
}

function CharacterCard({ character }: { character: Character }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-2">
      {/* Header with portrait */}
      <div className="flex items-start gap-3">
        <CharacterAvatar character={character} />

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5">
                <h3 className="text-sm font-bold text-slate-100 truncate">
                  {character.name}
                </h3>
                <MoodBadge mood={character.mood} />
              </div>
              <p className="text-xs text-slate-400">{character.public_role}</p>
            </div>
            <span className="shrink-0 text-xs bg-cyan-900/40 text-cyan-300 border border-cyan-700/40 rounded px-2 py-0.5 flex items-center gap-1">
              <span className="inline-block w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
              {character.location}
            </span>
          </div>
        </div>
      </div>

      {/* Bars */}
      <div className="space-y-1.5">
        <SuspicionBar value={character.suspicion} />
        <TrustBar value={character.trust_to_player} />
      </div>
    </div>
  );
}

export default function CharacterPanel({ characters }: CharacterPanelProps) {
  return (
    <div className="space-y-2">
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider px-1">
        角色
      </h2>
      {characters.length === 0 ? (
        <p className="text-xs text-slate-500 px-1">等待角色登场...</p>
      ) : (
        <div className="space-y-2">
          {characters.map((char) => (
            <CharacterCard key={char.id} character={char} />
          ))}
        </div>
      )}
    </div>
  );
}
