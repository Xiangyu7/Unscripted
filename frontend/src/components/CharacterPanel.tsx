"use client";

import React from "react";
import { Character } from "@/lib/types";

interface CharacterPanelProps {
  characters: Character[];
}

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

function CharacterCard({ character }: { character: Character }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-2">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-slate-100 truncate">
            {character.name}
          </h3>
          <p className="text-xs text-slate-400">{character.public_role}</p>
        </div>
        <span className="shrink-0 text-xs bg-slate-700 text-slate-300 rounded px-1.5 py-0.5">
          {character.location}
        </span>
      </div>

      {/* Style tag */}
      <div>
        <span className="inline-block text-xs text-violet-400 bg-violet-900/30 rounded px-1.5 py-0.5">
          {character.style}
        </span>
      </div>

      {/* Bars */}
      <div className="space-y-1.5">
        <SuspicionBar value={character.suspicion} />
        <TrustBar value={character.trust_to_player} />
      </div>

      {/* Goal */}
      <p className="text-xs text-slate-500 leading-snug">
        <span className="text-slate-600">目标: </span>
        {character.goal}
      </p>
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
