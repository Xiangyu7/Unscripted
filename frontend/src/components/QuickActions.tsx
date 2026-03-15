"use client";

import React, { useMemo } from "react";
import { Character, Clue } from "@/lib/types";

interface QuickActionsProps {
  onAction: (action: string) => void;
  disabled: boolean;
  scene?: string;
  characters?: Character[];
  clues?: Clue[];
  round?: number;
  tension?: number;
}

// Context-aware action suggestions
function buildActions(
  scene: string,
  characters: Character[],
  clues: Clue[],
  round: number,
  tension: number,
): string[] {
  const actions: string[] = [];
  const discoveredClues = clues.filter((c) => c.discovered);
  const currentChars = characters.filter((c) => c.location === scene || scene.includes(c.location));
  const shortScene = ["宴会厅", "书房", "花园", "酒窖", "走廊"].find((s) => scene.includes(s)) || scene;

  // Always useful: observe current scene
  actions.push(`仔细观察${shortScene}的每个角落`);

  // Talk to characters present
  for (const c of currentChars.slice(0, 2)) {
    if (c.trust_to_player > 40) {
      actions.push(`跟${c.name}聊聊顾言最近的状况`);
    } else if (c.suspicion > 50) {
      actions.push(`质问${c.name}，追问可疑之处`);
    } else {
      actions.push(`试探${c.name}，看看反应`);
    }
  }

  // Location-specific searches
  if (shortScene === "宴会厅") {
    if (!discoveredClues.some((c) => c.id === "anonymous_tip")) {
      actions.push("翻翻垃圾桶和角落");
    }
    if (tension >= 45 && !discoveredClues.some((c) => c.id === "linlan_phone_log")) {
      actions.push("趁林岚不注意偷看她的手机");
    }
  } else if (shortScene === "书房") {
    if (!discoveredClues.some((c) => c.id === "study_scratches")) {
      actions.push("检查书房门把手和桌面");
    }
    if (!discoveredClues.some((c) => c.id === "will_draft")) {
      actions.push("打开书桌抽屉翻翻看");
    }
    if (tension >= 55 && !discoveredClues.some((c) => c.id === "staged_evidence")) {
      actions.push("仔细检查这个'失踪现场'是否有人为布置的痕迹");
    }
  } else if (shortScene === "酒窖") {
    if (!discoveredClues.some((c) => c.id === "wine_cellar_footprint")) {
      actions.push("检查酒窖入口和地面");
    }
    if (!discoveredClues.some((c) => c.id === "cellar_sound")) {
      actions.push("仔细听听酒窖深处有没有声音");
    }
    if (!discoveredClues.some((c) => c.id === "cellar_provisions")) {
      actions.push("搜查酒窖的每个角落");
    }
  } else if (shortScene === "花园") {
    if (!discoveredClues.some((c) => c.id === "torn_letter")) {
      actions.push("搜查花园灌木丛和长椅周围");
    }
  }

  // Movement suggestions - suggest unvisited locations
  const otherLocations = ["宴会厅", "书房", "花园", "酒窖"].filter(
    (loc) => !scene.includes(loc)
  );
  if (otherLocations.length > 0) {
    actions.push(`去${otherLocations[0]}看看`);
  }

  // Clue-based follow-up actions
  if (discoveredClues.some((c) => c.id === "will_draft")) {
    const linlan = characters.find((c) => c.id === "linlan");
    if (linlan && linlan.location === shortScene) {
      actions.push("拿遗嘱草稿质问林岚");
    }
  }
  if (discoveredClues.some((c) => c.id === "cellar_sound") && !scene.includes("酒窖")) {
    actions.push("去酒窖深处找那个声音的来源");
  }

  // Late game
  if (round >= 12 && discoveredClues.length >= 4) {
    actions.push("发起公开对峙");
  }

  return actions.slice(0, 6);
}

export default function QuickActions({
  onAction,
  disabled,
  scene = "",
  characters = [],
  clues = [],
  round = 0,
  tension = 0,
}: QuickActionsProps) {
  const actions = useMemo(
    () => buildActions(scene, characters, clues, round, tension),
    [scene, characters, clues, round, tension]
  );

  return (
    <div className="px-4 pb-3">
      <div className="flex flex-wrap gap-1.5">
        {actions.map((action) => (
          <button
            key={action}
            onClick={() => onAction(action)}
            disabled={disabled}
            className="btn-transition text-xs px-2.5 py-1.5 rounded-full border border-slate-600 text-slate-400 hover:text-amber-300 hover:border-amber-600/50 hover:bg-amber-950/20 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:text-slate-400 disabled:hover:border-slate-600 disabled:hover:bg-transparent"
          >
            {action}
          </button>
        ))}
      </div>
    </div>
  );
}
