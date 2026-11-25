import React, { useMemo, useState } from "react";
import {
  Activity,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Globe,
  Mic,
  MicOff,
  Radio,
  Search,
  Settings,
  Sparkles,
  Terminal,
  Volume2,
  X,
} from "lucide-react";
import { ALL_PAGES, ModuleId, PageDef } from "../catalog/navigation";
import { DeviceProfile } from "../lib/device";

interface MasterSchematicViewProps {
  device: DeviceProfile;
  activeModule: ModuleId;
  activeSubPage: string;
  onNavigate: (moduleId: ModuleId, subPageId?: string) => void;
  onDispatchToTerminal?: (prompt: string, voice?: boolean) => void;
  onOpenSettings?: () => void;
}

// Procedural SVG wireframe globe/radar matching the technical HUD in IMG_0782.jpeg
function HudSphereGraphic({ num, color }: { num: number; color?: string }) {
  const stroke = color || (num <= 90 ? "#cbd5e1" : num <= 96 ? "#fb923c" : num <= 111 ? "#f87171" : "#38bdf8");
  const mod3 = num % 3;
  const mod4 = num % 4;

  return (
    <svg viewBox="0 0 44 44" className="w-full h-full" style={{ maxHeight: 28 }} fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Outer orbit circle */}
      <circle cx="22" cy="22" r="17" stroke={stroke} strokeWidth="0.75" strokeOpacity="0.45" />
      {/* Horizontal latitude ellipse */}
      <ellipse cx="22" cy="22" rx="17" ry={mod3 === 0 ? 5 : mod3 === 1 ? 8 : 12} stroke={stroke} strokeWidth="0.65" strokeOpacity="0.7" />
      {/* Vertical longitude ellipse */}
      <ellipse cx="22" cy="22" rx={mod4 === 0 ? 6 : mod4 === 1 ? 10 : 14} ry="17" stroke={stroke} strokeWidth="0.65" strokeOpacity="0.7" />
      {/* Axial lines */}
      <line x1="5" y1="22" x2="39" y2="22" stroke={stroke} strokeWidth="0.5" strokeOpacity="0.5" strokeDasharray={num % 2 === 0 ? "1 1" : undefined} />
      <line x1="22" y1="5" x2="22" y2="39" stroke={stroke} strokeWidth="0.5" strokeOpacity="0.5" />
      {/* Core node */}
      <circle cx="22" cy="22" r="1.5" fill={stroke} fillOpacity="0.9" />
      {/* Peripheral data satellite node */}
      {num % 2 === 1 && (
        <circle cx={14 + (num % 16)} cy={12 + ((num * 3) % 20)} r="1.2" fill={stroke} />
      )}
    </svg>
  );
}

export function MasterSchematicView({
  device,
  activeModule,
  activeSubPage,
  onNavigate,
  onDispatchToTerminal,
  onOpenSettings,
}: MasterSchematicViewProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [hoveredPage, setHoveredPage] = useState<PageDef | null>(null);

  // Group pages by the 4 authoritative schematic zones from IMG_0782.jpeg
  const systemsPages = useMemo(() => ALL_PAGES.filter((p) => p.number >= 1 && p.number <= 90), []);
  const orbitPages = useMemo(() => ALL_PAGES.filter((p) => p.number >= 91 && p.number <= 96), []);
  const settingsPages = useMemo(() => ALL_PAGES.filter((p) => p.number >= 97 && p.number <= 111), []);
  const terminalPage = useMemo(() => ALL_PAGES.find((p) => p.number === 112), []);

  const handleToggleVoice = () => {
    if (typeof window === "undefined") return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please use keyboard command input.");
      return;
    }
    if (isListening) {
      setIsListening(false);
      return;
    }
    try {
      const recognition = new SpeechRecognition();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      setIsListening(true);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setSearchQuery(transcript);
        setIsListening(false);
        if (onDispatchToTerminal && transcript.trim().length > 2) {
          onDispatchToTerminal(transcript, true);
        }
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);
      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const handleCommandSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) return;
    if (onDispatchToTerminal) {
      onDispatchToTerminal(searchQuery.trim());
    } else {
      // Find matching page or navigate to terminal
      const match = ALL_PAGES.find(
        (p) =>
          p.pageId === searchQuery.trim().padStart(3, "0") ||
          p.label.toLowerCase().includes(searchQuery.toLowerCase().trim())
      );
      if (match) {
        onNavigate(match.module, match.id);
      } else {
        onNavigate("terminal", "master-terminal");
      }
    }
  };

  const renderCard = (p: PageDef, zoneColor?: string, extraClass?: string) => {
    const isCurrent = activeModule === p.module && activeSubPage === p.id;
    const redLabel = `#ef4444`;

    return (
      <button
        key={p.pageId}
        type="button"
        onClick={() => onNavigate(p.module, p.id)}
        onMouseEnter={() => setHoveredPage(p)}
        onMouseLeave={() => setHoveredPage(null)}
        className={`group relative text-left rounded-[3px] transition-all flex flex-col justify-between overflow-hidden cursor-pointer select-none ${
          isCurrent
            ? "ring-1 ring-cyan-400 bg-slate-900 shadow-[0_0_8px_rgba(56,189,248,0.5)]"
            : "bg-[#090d15] hover:bg-[#121927] hover:ring-1 hover:ring-zinc-400"
        } ${extraClass || ""}`}
        style={{
          backgroundColor: isCurrent ? "#0f172a" : "#070c16",
          color: "#f8fafc",
          border: isCurrent
            ? "1.5px solid #38bdf8"
            : zoneColor
            ? `1px solid ${zoneColor}`
            : "1px solid rgba(255, 255, 255, 0.12)",
          padding: "3px 4px 2px 4px",
          minHeight: 46,
          boxShadow: isCurrent ? "0 0 10px rgba(56,189,248,0.3)" : "inset 0 1px 0 rgba(255,255,255,0.06)",
        }}
        title={`[PAGE ${p.pageId}] ${p.label} · ${p.subsystem} (${p.primaryAgent || "SYS"})`}
      >
        {/* Top mini telemetry header */}
        <div className="flex items-center justify-between w-full opacity-85 leading-none">
          <div className="flex items-center gap-0.5">
            <span className="w-1 h-1 rounded-full bg-cyan-400/80" />
            <span className="font-mono text-[7px] text-zinc-400 tracking-tighter truncate max-w-[50px]">
              {p.primaryAgent || "SYS"}
            </span>
          </div>
          <span className="w-1 h-1 rounded-full" style={{ background: zoneColor || "#10b981" }} />
        </div>

        {/* Center: Miniature HUD wireframe sphere graphic */}
        <div className="my-0.5 w-full flex items-center justify-center opacity-90 group-hover:scale-105 transition-transform">
          <HudSphereGraphic num={p.number} color={zoneColor} />
        </div>

        {/* Bottom Red Monospace Page Identifier matching IMG_0782.jpeg */}
        <div className="w-full flex items-center justify-center mt-0.5">
          <span
            className="font-mono text-[8px] font-black tracking-wider text-center"
            style={{ color: redLabel, textShadow: "0 0 6px rgba(239,68,68,0.4)" }}
          >
            PAGE {p.pageId}
          </span>
        </div>
      </button>
    );
  };

  return (
    <div className="ultron-hardware-chassis select-none" data-testid="ultron-master-schematic">
      {/* Titanium Sculpted Chassis Frame matching IMG_0782.jpeg */}
      <div className="ultron-titanium-bezel">
        {/* ==============================================================
            MASTER HEADER (IMG_0782.jpeg TOP BAR)
            ============================================================== */}
        <header className="flex items-center justify-between w-full mb-3 pb-2 border-b border-zinc-700/50">
          {/* Left: Aperture emblem + Title Lockup */}
          <div className="flex items-center gap-2.5 sm:gap-3">
            {/* Dual Concentric Ring Metallic Aperture Logo */}
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center relative shrink-0"
              style={{
                border: "1.5px solid #94a3b8",
                background: "radial-gradient(circle, #0f172a 0%, #020617 100%)",
                boxShadow: "0 0 10px rgba(56, 189, 248, 0.4), inset 0 0 6px rgba(56, 189, 248, 0.3)",
              }}
            >
              <div className="w-4 h-4 rounded-full border border-cyan-400/80 flex items-center justify-center">
                <div className="w-1.5 h-1.5 rounded-full bg-cyan-300 shadow-[0_0_6px_#38bdf8]" />
              </div>
            </div>

            <div className="flex flex-col leading-none">
              <span className="font-mono text-xs sm:text-sm font-black tracking-widest text-zinc-100 flex items-center gap-1">
                ULTRON <span className="text-zinc-500 font-light">/</span>
              </span>
              <span className="font-mono text-[9px] sm:text-[11px] font-bold tracking-widest text-zinc-300 uppercase mt-0.5">
                MOBILE INTERFACE MASTER SCHEMATIC
              </span>
            </div>
          </div>

          {/* Right: Status Telemetry Pill & Controls */}
          <div className="flex items-center gap-2 sm:gap-3">
            <span
              className="font-mono text-[9px] sm:text-[11px] font-black tracking-widest text-emerald-400 flex items-center gap-1 px-1.5 py-0.5 rounded"
              style={{ background: "rgba(16, 185, 129, 0.12)", border: "1px solid rgba(16, 185, 129, 0.3)" }}
            >
              STATUS: VERIFIED
            </span>

            <span className="text-zinc-600 font-mono text-xs hidden sm:inline">|</span>

            <span className="font-mono text-[9px] sm:text-[11px] font-bold tracking-widest text-zinc-100 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-white shadow-[0_0_8px_#ffffff] animate-pulse" />
              ONLINE
            </span>

            <button
              type="button"
              onClick={() => {
                if (onOpenSettings) onOpenSettings();
                else onNavigate("settings", "general");
              }}
              style={{ background: "transparent", border: "none", cursor: "pointer" }}
              className="p-1 rounded text-zinc-400 hover:text-white transition-colors ml-1 flex items-center justify-center"
              title="System Settings"
            >
              <Settings size={15} />
            </button>
          </div>
        </header>

        {/* Hover Inspector Banner (Contextual Page Information) */}
        <div className="h-5 mb-2 px-2 flex items-center justify-between text-zinc-300 font-mono text-[10px] bg-slate-900/60 rounded border border-zinc-800/80">
          {hoveredPage ? (
            <>
              <span className="text-cyan-400 font-bold truncate">
                PAGE {hoveredPage.pageId} · {hoveredPage.label.toUpperCase()}
              </span>
              <span className="text-zinc-400 truncate ml-2 hidden sm:inline">
                {hoveredPage.subsystem} · PRIMARY: {hoveredPage.primaryAgent || "SYS"} · [{hoveredPage.integrationStatus || "VERIFIED"}]
              </span>
            </>
          ) : (
            <span className="text-zinc-400 tracking-wider">
              112-PAGE AUTHORITATIVE MATRIX · TAP ANY CELL TO LAUNCH OPERATIONAL INTERFACE
            </span>
          )}
        </div>

        {/* ==============================================================
            MASTER MATRIX GRID WITH 4 PRECISE ZONES (IMG_0782.jpeg)
            ============================================================== */}
        <div className="flex-1 flex flex-col gap-2.5 overflow-y-auto pr-1">
          {/* Top Pill for 01-90 */}
          <div className="flex items-center justify-center">
            <span
              className="font-mono text-[10px] font-black uppercase tracking-widest px-3 py-0.5 rounded-full"
              style={{
                background: "rgba(30, 41, 59, 0.8)",
                color: "#e2e8f0",
                border: "1px solid rgba(148, 163, 184, 0.3)",
                boxShadow: "0 2px 8px rgba(0,0,0,0.5)",
              }}
            >
              01-90 SYSTEMS &amp; DIAGNOSTICS
            </span>
          </div>

          {/* ZONE 1: 01-90 SYSTEMS & DIAGNOSTICS */}
          <div className="flex flex-col">
            <div
              className="grid gap-1"
              style={{
                gridTemplateColumns: "repeat(auto-fill, minmax(76px, 1fr))",
              }}
            >
              {systemsPages.map((p) => renderCard(p))}
            </div>
          </div>

          {/* LOWER MATRIX: ZONE 2 (91-96 ORBIT) + ZONE 3 (97-111 SETTINGS) + ZONE 4 (112 MASTER TERMINAL) */}
          <div className="grid grid-cols-1 md:grid-cols-12 gap-2 mt-1">
            {/* ZONE 2: 91-96 ORBIT DEVICE MANAGEMENT (Glowing Orange Enclosure) */}
            <div
              className="md:col-span-4 rounded-lg p-2 flex flex-col gap-1.5"
              style={{
                background: "rgba(249, 115, 22, 0.05)",
                border: "2px solid #f97316",
                boxShadow: "0 0 16px rgba(249, 115, 22, 0.3), inset 0 0 12px rgba(249, 115, 22, 0.1)",
              }}
            >
              <div className="flex items-center justify-between">
                <span
                  className="font-mono text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full"
                  style={{
                    background: "rgba(249, 115, 22, 0.2)",
                    color: "#fb923c",
                    border: "1px solid #f97316",
                  }}
                >
                  91-96 ORBIT DEVICE MANAGEMENT
                </span>
                <span className="font-mono text-[8px] text-orange-400 font-bold">6 NODES</span>
              </div>
              <div className="grid gap-1 grid-cols-3 sm:grid-cols-6">
                {orbitPages.map((p) => renderCard(p, "#f97316"))}
              </div>
            </div>

            {/* ZONE 3: 97-111 SETTINGS (Glowing Crimson Red Enclosure) */}
            <div
              className="md:col-span-6 rounded-lg p-2 flex flex-col gap-1.5"
              style={{
                background: "rgba(239, 68, 68, 0.05)",
                border: "2px solid #ef4444",
                boxShadow: "0 0 18px rgba(239, 68, 68, 0.35), inset 0 0 12px rgba(239, 68, 68, 0.1)",
              }}
            >
              <div className="flex items-center justify-between">
                <span
                  className="font-mono text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full"
                  style={{
                    background: "rgba(239, 68, 68, 0.2)",
                    color: "#f87171",
                    border: "1px solid #ef4444",
                  }}
                >
                  97-111 SETTINGS
                </span>
                <span className="font-mono text-[8px] text-red-400 font-bold">15 CONTROLS</span>
              </div>
              <div className="grid gap-1 grid-cols-5 sm:grid-cols-5">
                {settingsPages.map((p) => renderCard(p, "#ef4444"))}
              </div>
            </div>

            {/* ZONE 4: 112 MASTER TERMINAL (Glowing Cyan Enclosure) */}
            <div
              className="md:col-span-2 rounded-lg p-2 flex flex-col justify-between"
              style={{
                background: "rgba(56, 189, 248, 0.08)",
                border: "2px solid #38bdf8",
                boxShadow: "0 0 18px rgba(56, 189, 248, 0.4), inset 0 0 12px rgba(56, 189, 248, 0.15)",
              }}
            >
              <span
                className="font-mono text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full text-center"
                style={{
                  background: "rgba(56, 189, 248, 0.2)",
                  color: "#38bdf8",
                  border: "1px solid #38bdf8",
                }}
              >
                112 MASTER TERMINAL
              </span>
              <div className="my-1">
                {terminalPage && renderCard(terminalPage, "#38bdf8")}
              </div>
            </div>
          </div>
        </div>

        {/* ==============================================================
            BOTTOM COMMAND BAR & ZONE 4 (112 MASTER TERMINAL)
            ============================================================== */}
        <footer className="mt-3 pt-2 border-t border-zinc-800 flex flex-wrap items-center justify-between gap-3">
          {/* Globe Quick Launcher Thumbnail */}
          <button
            type="button"
            onClick={() => onNavigate("command", "overview")}
            className="flex items-center gap-2 p-1.5 rounded bg-slate-900 border border-zinc-700/80 hover:border-cyan-400 transition-colors"
            title="Open Global System Overview (Page 002)"
          >
            <div className="w-6 h-6 rounded-full bg-cyan-950/60 border border-cyan-400 flex items-center justify-center">
              <Globe size={13} className="text-cyan-400" />
            </div>
            <span className="font-mono text-[9px] text-zinc-300 font-bold hidden sm:inline">GLOBAL</span>
          </button>

          {/* Natural Language Command Bar matching IMG_0782.jpeg */}
          <form
            onSubmit={handleCommandSubmit}
            className="flex-1 max-w-2xl relative flex items-center"
          >
            <div className="relative w-full flex items-center">
              <button
                type="button"
                onClick={handleToggleVoice}
                className={`absolute left-2 p-1.5 rounded-full z-10 transition-colors ${
                  isListening
                    ? "bg-red-500 text-white animate-pulse"
                    : "text-zinc-400 hover:text-cyan-400"
                }`}
                title={isListening ? "Listening..." : "Click to speak voice command"}
              >
                {isListening ? <Mic size={14} /> : <Mic size={14} />}
              </button>

              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Ask ULTRON anything or explore page master..."
                className="w-full pl-8 pr-10 py-2 rounded-full font-sans text-xs text-zinc-100 placeholder-zinc-500 bg-[#060a12] border border-zinc-700/80 focus:border-cyan-400 focus:outline-none focus:ring-1 focus:ring-cyan-400 transition-all shadow-[inset_0_2px_4px_rgba(0,0,0,0.8)]"
              />

              <button
                type="submit"
                className="absolute right-2 p-1 rounded-full text-zinc-400 hover:text-cyan-400 transition-colors"
                title="Execute Command"
              >
                <Search size={14} />
              </button>
            </div>
          </form>

          {/* ZONE 4: 112 MASTER TERMINAL (Far Right Container) */}
          {terminalPage && (
            <div
              className="flex items-center gap-1.5 p-1 rounded bg-slate-900/80 border border-cyan-400 hover:bg-slate-800 transition-colors cursor-pointer shadow-[0_0_12px_rgba(56,189,248,0.25)]"
              onClick={() => onNavigate("terminal", "master-terminal")}
              title="Launch ULTRON Master Terminal (Page 112)"
            >
              <div className="w-7 h-7 rounded flex items-center justify-center bg-cyan-950/60 border border-cyan-400">
                <Terminal size={14} className="text-cyan-400" />
              </div>
              <div className="flex flex-col pr-1">
                <span
                  className="font-mono text-[8px] font-black uppercase tracking-wider px-1 py-0.2 rounded"
                  style={{
                    background: "rgba(56, 189, 248, 0.2)",
                    color: "#38bdf8",
                    border: "1px solid #38bdf8",
                  }}
                >
                  112 MASTER TERMINAL
                </span>
                <span className="font-mono text-[7px] text-zinc-400 mt-0.5">DIRECT DISPATCH</span>
              </div>
            </div>
          )}
        </footer>
      </div>
    </div>
  );
}
