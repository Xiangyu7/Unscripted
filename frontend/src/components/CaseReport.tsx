"use client";

import React, { useRef, useCallback } from "react";

interface ReportClue {
  id: string;
  text: string;
  location: string;
}

interface ReportEvent {
  round: number;
  type: string;
  text: string;
}

interface ReportCharacter {
  id: string;
  name: string;
  trust: number;
  suspicion: number;
}

interface CaseReportData {
  session_id: string;
  title: string;
  game_over: boolean;
  ending: string | null;
  round: number;
  max_rounds: number;
  tension: number;
  discovered_clues: ReportClue[];
  total_clues: number;
  key_events: ReportEvent[];
  characters: ReportCharacter[];
}

interface CaseReportProps {
  data: CaseReportData;
  onClose: () => void;
}

export default function CaseReport({ data, onClose }: CaseReportProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  const handleDownload = useCallback(async () => {
    if (!cardRef.current) return;
    try {
      const { toPng } = await import("html-to-image");
      const dataUrl = await toPng(cardRef.current, {
        backgroundColor: "#0f172a",
        pixelRatio: 2,
      });
      const link = document.createElement("a");
      link.download = `detective-report-${data.session_id.slice(0, 8)}.png`;
      link.href = dataUrl;
      link.click();
    } catch {
      // Fallback: copy text summary
      const summary = `${data.title}\n回合: ${data.round}/${data.max_rounds}\n线索: ${data.discovered_clues.length}/${data.total_clues}\n紧张度: ${data.tension}`;
      await navigator.clipboard.writeText(summary).catch(() => {});
    }
  }, [data]);

  const cluePct = data.total_clues > 0
    ? Math.round((data.discovered_clues.length / data.total_clues) * 100)
    : 0;

  return (
    <div className="fixed inset-0 bg-black/70 z-50 flex items-center justify-center p-4">
      <div className="max-w-lg w-full max-h-[90vh] overflow-y-auto">
        <div
          ref={cardRef}
          className="bg-slate-900 border border-amber-700/40 rounded-xl p-6 space-y-4"
        >
          {/* Header */}
          <div className="text-center">
            <h2 className="text-xl font-bold text-amber-400">{data.title}</h2>
            <p className="text-slate-400 text-sm mt-1">侦探档案</p>
          </div>

          {/* Stats grid */}
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="bg-slate-800/60 rounded-lg p-3">
              <div className="text-2xl font-bold text-slate-200">{data.round}</div>
              <div className="text-xs text-slate-500">回合</div>
            </div>
            <div className="bg-slate-800/60 rounded-lg p-3">
              <div className="text-2xl font-bold text-amber-400">
                {data.discovered_clues.length}/{data.total_clues}
              </div>
              <div className="text-xs text-slate-500">线索 ({cluePct}%)</div>
            </div>
            <div className="bg-slate-800/60 rounded-lg p-3">
              <div className={`text-2xl font-bold ${
                data.tension >= 65 ? "text-red-400" : data.tension >= 35 ? "text-yellow-400" : "text-emerald-400"
              }`}>
                {data.tension}
              </div>
              <div className="text-xs text-slate-500">紧张度</div>
            </div>
          </div>

          {/* Discovered clues */}
          {data.discovered_clues.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-amber-400 mb-2">发现的线索</h3>
              <div className="space-y-1">
                {data.discovered_clues.map((clue) => (
                  <div key={clue.id} className="text-xs text-slate-400 flex items-start gap-1.5">
                    <span className="text-amber-500 mt-0.5">&#8226;</span>
                    <span>{clue.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Key events */}
          {data.key_events.length > 0 && (
            <div>
              <h3 className="text-sm font-medium text-red-400 mb-2">关键时刻</h3>
              <div className="space-y-1">
                {data.key_events.slice(0, 5).map((evt, i) => (
                  <div key={i} className="text-xs text-slate-400 flex items-start gap-1.5">
                    <span className="text-red-500 text-[10px] mt-0.5">R{evt.round}</span>
                    <span>{evt.text.slice(0, 60)}{evt.text.length > 60 ? "..." : ""}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Characters */}
          <div>
            <h3 className="text-sm font-medium text-cyan-400 mb-2">人物关系</h3>
            <div className="flex gap-2">
              {data.characters.map((char) => (
                <div key={char.id} className="flex-1 bg-slate-800/40 rounded-lg p-2 text-center">
                  <div className="text-sm font-medium text-slate-200">{char.name}</div>
                  <div className="text-[10px] text-slate-500 mt-1">
                    信任 <span className={char.trust >= 50 ? "text-emerald-400" : "text-red-400"}>{char.trust}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Footer */}
          <div className="text-center text-[10px] text-slate-600 pt-2 border-t border-slate-800">
            Unscripted - AI Detective Game
          </div>
        </div>

        {/* Action buttons (outside the screenshot area) */}
        <div className="flex gap-3 mt-3 justify-center">
          <button
            onClick={handleDownload}
            className="px-4 py-2 text-sm bg-amber-700 hover:bg-amber-600 text-white rounded-lg transition-colors"
          >
            下载图片
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg transition-colors"
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
