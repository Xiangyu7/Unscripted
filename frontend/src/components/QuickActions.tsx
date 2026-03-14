"use client";

import React from "react";

interface QuickActionsProps {
  onAction: (action: string) => void;
  disabled: boolean;
}

const PRESET_ACTIONS = [
  "观察所有人的表情和站位",
  "去问林岚，顾言失踪前最后见过谁",
  "诈周牧，说我已经知道昨晚发生了什么",
  "搜查书房",
  "公开指出这件事和遗嘱有关",
  "前往酒窖看看",
  "偷听林岚和周牧的对话",
];

export default function QuickActions({
  onAction,
  disabled,
}: QuickActionsProps) {
  return (
    <div className="px-4 pb-3">
      <div className="flex flex-wrap gap-1.5">
        {PRESET_ACTIONS.map((action) => (
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
