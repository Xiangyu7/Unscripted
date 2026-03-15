"use client";

import React from "react";
import { Character } from "@/lib/types";

interface LocationMapProps {
  characters: Character[];
  playerScene: string;
  className?: string;
}

/* ── colour map per NPC ── */
const CHARACTER_COLORS: Record<string, { dot: string; badge: string; text: string }> = {
  linlan: {
    dot: "bg-cyan-400",
    badge: "bg-cyan-900/40 border-cyan-700/40",
    text: "text-cyan-300",
  },
  zhoumu: {
    dot: "bg-orange-400",
    badge: "bg-orange-900/40 border-orange-700/40",
    text: "text-orange-300",
  },
  songzhi: {
    dot: "bg-purple-400",
    badge: "bg-purple-900/40 border-purple-700/40",
    text: "text-purple-300",
  },
};

const DEFAULT_COLOR = {
  dot: "bg-slate-400",
  badge: "bg-slate-700/40 border-slate-600/40",
  text: "text-slate-300",
};

/*
 * Adjacency (visual layout):
 *
 *          书房 ── 走廊 ── 花园
 *                   │
 *                 宴会厅
 *                   │
 *                  酒窖
 *
 * Grid (5 cols x 5 rows) — locations pinned to cells:
 *   书房  (col 1, row 1)
 *   走廊  (col 3, row 1)
 *   花园  (col 5, row 1)
 *   宴会厅 (col 3, row 3)
 *   酒窖  (col 3, row 5)
 */

interface LocationDef {
  id: string;
  label: string;
  col: number; // 1-based grid column
  row: number; // 1-based grid row
}

const LOCATIONS: LocationDef[] = [
  { id: "书房", label: "书房", col: 1, row: 1 },
  { id: "走廊", label: "走廊", col: 3, row: 1 },
  { id: "花园", label: "花园", col: 5, row: 1 },
  { id: "宴会厅", label: "宴会厅", col: 3, row: 3 },
  { id: "酒窖", label: "酒窖", col: 3, row: 5 },
];

/* Edges drawn as thin lines between adjacent locations. Each edge sits in
   the grid cell *between* two location cells. */
interface EdgeDef {
  col: number;
  row: number;
  direction: "h" | "v"; // horizontal or vertical
}

const EDGES: EdgeDef[] = [
  { col: 2, row: 1, direction: "h" }, // 书房 ── 走廊
  { col: 4, row: 1, direction: "h" }, // 走廊 ── 花园
  { col: 3, row: 2, direction: "v" }, // 走廊 ── 宴会厅
  { col: 3, row: 4, direction: "v" }, // 宴会厅 ── 酒窖
];

function CharacterBadge({ character }: { character: Character }) {
  const colors = CHARACTER_COLORS[character.id] ?? DEFAULT_COLOR;
  return (
    <span
      className={`inline-flex items-center gap-1 text-[10px] leading-none font-medium rounded px-1 py-0.5 border ${colors.badge} ${colors.text}`}
    >
      <span className={`inline-block w-1.5 h-1.5 rounded-full ${colors.dot}`} />
      {character.name}
    </span>
  );
}

function LocationNode({
  location,
  isPlayerHere,
  occupants,
}: {
  location: LocationDef;
  isPlayerHere: boolean;
  occupants: Character[];
}) {
  return (
    <div
      className={`
        relative flex flex-col items-center justify-center gap-1
        rounded-lg border px-2 py-2 min-h-[56px]
        transition-colors duration-300
        ${
          isPlayerHere
            ? "bg-amber-950/40 border-amber-600/60 shadow-[0_0_8px_rgba(245,158,11,0.15)]"
            : "bg-slate-800 border-slate-700"
        }
      `}
      style={{
        gridColumn: location.col,
        gridRow: location.row,
      }}
    >
      {/* Location name */}
      <span
        className={`text-xs font-bold whitespace-nowrap ${
          isPlayerHere ? "text-amber-400" : "text-slate-300"
        }`}
      >
        {location.label}
      </span>

      {/* Player indicator */}
      {isPlayerHere && (
        <span className="text-[9px] text-amber-500/80 font-medium">
          [你在此]
        </span>
      )}

      {/* NPC badges */}
      {occupants.length > 0 && (
        <div className="flex flex-wrap justify-center gap-0.5 mt-0.5">
          {occupants.map((c) => (
            <CharacterBadge key={c.id} character={c} />
          ))}
        </div>
      )}
    </div>
  );
}

function Edge({ edge }: { edge: EdgeDef }) {
  return (
    <div
      className="flex items-center justify-center"
      style={{
        gridColumn: edge.col,
        gridRow: edge.row,
      }}
    >
      {edge.direction === "h" ? (
        <div className="w-full h-px bg-slate-600" />
      ) : (
        <div className="h-full w-px bg-slate-600 mx-auto" />
      )}
    </div>
  );
}

export default function LocationMap({
  characters,
  playerScene,
  className = "",
}: LocationMapProps) {
  /* Group characters by location */
  const occupantsByLocation: Record<string, Character[]> = {};
  for (const c of characters) {
    if (!occupantsByLocation[c.location]) {
      occupantsByLocation[c.location] = [];
    }
    occupantsByLocation[c.location].push(c);
  }

  return (
    <div className={`space-y-2 ${className}`}>
      <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider px-1">
        顾家老宅
      </h2>

      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: "1fr auto 1fr auto 1fr",
          gridTemplateRows: "auto auto auto auto auto",
        }}
      >
        {/* Edges (drawn behind nodes in DOM order, but grid overlap is fine) */}
        {EDGES.map((e, i) => (
          <Edge key={`edge-${i}`} edge={e} />
        ))}

        {/* Location nodes */}
        {LOCATIONS.map((loc) => (
          <LocationNode
            key={loc.id}
            location={loc}
            isPlayerHere={playerScene === loc.id}
            occupants={occupantsByLocation[loc.id] ?? []}
          />
        ))}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-1 pt-1 border-t border-slate-700/50">
        <span className="text-[10px] text-slate-500">图例:</span>
        {Object.entries(CHARACTER_COLORS).map(([id, colors]) => {
          const char = characters.find((c) => c.id === id);
          const label = char?.name ?? id;
          return (
            <span
              key={id}
              className={`inline-flex items-center gap-1 text-[10px] ${colors.text}`}
            >
              <span
                className={`inline-block w-1.5 h-1.5 rounded-full ${colors.dot}`}
              />
              {label}
            </span>
          );
        })}
        <span className="inline-flex items-center gap-1 text-[10px] text-amber-500">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-400" />
          你
        </span>
      </div>
    </div>
  );
}
