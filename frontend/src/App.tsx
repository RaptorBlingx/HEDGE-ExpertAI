import { motion } from "framer-motion";
import {
  AlertCircle,
  Bot,
  CheckCircle2,
  Database,
  RefreshCw,
  Search,
  SendHorizontal,
  Sparkles,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { CatalogApp, CatalogResponse, RecommendedApp } from "./types";

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  apps: RecommendedApp[];
  responseTimeMs?: number;
  isStreaming?: boolean;
};

type IntentHint = "search" | "detail" | "help" | "greeting" | "unknown";

const DEFAULT_ASSISTANT_MESSAGE =
  "Welcome to the HEDGE-ExpertAI validation console. Browse the catalog on the left, ask the chatbot on the right, and cross-check recommendations instantly.";

const THINKING_STEPS: Record<IntentHint, string[]> = {
  search: [
    "Interpreting your request and extracting domain intent.",
    "Scanning indexed applications across semantic and keyword signals.",
    "Prioritizing strongest matches based on metadata relevance.",
    "Drafting a concise, evidence-based recommendation response.",
  ],
  detail: [
    "Resolving the referenced app and loading full metadata.",
    "Cross-checking domain, tags, and dataset signals.",
    "Building a focused explanation around your specific request.",
  ],
  help: [
    "Detecting assistance intent and preparing guidance.",
    "Selecting the most useful interaction examples.",
    "Formatting quick-start instructions for the test bench.",
  ],
  greeting: [
    "Detecting conversational greeting intent.",
    "Preparing a compact onboarding response.",
    "Finalizing a friendly welcome message.",
  ],
  unknown: [
    "Clarifying ambiguous intent from your prompt.",
    "Applying fallback retrieval strategy on catalog metadata.",
    "Preparing the most likely helpful response.",
  ],
};

function inferIntentHint(message: string): IntentHint {
  const text = message.trim().toLowerCase();
  if (!text) {
    return "unknown";
  }

  if (/^(hi|hello|hey|greetings|good\s*(morning|afternoon|evening))[\s!.,?]*$/i.test(text)) {
    return "greeting";
  }
  if (/\b(help|how\s+do\s+i|what\s+can\s+you\s+do|usage|guide|instructions)\b/i.test(text)) {
    return "help";
  }
  if (/\b(tell\s+me\s+(more\s+)?about|details?\s+(of|about|for)|explain|describe|app[-\s]?\d{3})\b/i.test(text)) {
    return "detail";
  }
  if (/\b(find|search|looking\s+for|show\s+me|recommend|suggest|discover|monitor|manage|detect|optimi[sz]e)\b/i.test(text)) {
    return "search";
  }

  return "unknown";
}

function formatDuration(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

function generateMessageId(): string {
  const maybeCrypto = globalThis.crypto;

  if (maybeCrypto && typeof maybeCrypto.randomUUID === "function") {
    return maybeCrypto.randomUUID();
  }

  if (maybeCrypto && typeof maybeCrypto.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    maybeCrypto.getRandomValues(bytes);

    // RFC 4122 v4 UUID bits
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;

    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, "0"));
    return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex.slice(6, 8).join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10, 16).join("")}`;
  }

  return `msg-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function normalizeRecommendedApps(items: unknown): RecommendedApp[] {
  if (!Array.isArray(items)) {
    return [];
  }

  return items.filter((item): item is RecommendedApp => {
    if (!item || typeof item !== "object") {
      return false;
    }
    const maybeApp = (item as { app?: { id?: string } }).app;
    return !!maybeApp && typeof maybeApp.id === "string";
  });
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleDateString();
}

async function fetchCatalog(): Promise<CatalogApp[]> {
  const response = await fetch("/api/v1/catalog/apps?page=1&page_size=100");
  if (!response.ok) {
    throw new Error("Failed to load app catalog");
  }
  const payload = (await response.json()) as CatalogResponse;
  return payload.apps ?? [];
}

export default function App() {
  const [apps, setApps] = useState<CatalogApp[]>([]);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [sarefFilter, setSarefFilter] = useState("all");
  const [selectedAppId, setSelectedAppId] = useState<string | null>(null);

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "assistant-welcome",
      role: "assistant",
      text: DEFAULT_ASSISTANT_MESSAGE,
      apps: [],
      responseTimeMs: 0,
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [activeIntentHint, setActiveIntentHint] = useState<IntentHint>("search");
  const [thinkingStepIndex, setThinkingStepIndex] = useState(0);
  const [activeResponseStartedAt, setActiveResponseStartedAt] = useState<number | null>(null);
  const [activeResponseElapsedMs, setActiveResponseElapsedMs] = useState(0);
  const [streamingMessageId, setStreamingMessageId] = useState<string | null>(null);

  const streamIntervalRef = useRef<number | null>(null);

  const loadCatalog = useCallback(async () => {
    setCatalogLoading(true);
    setCatalogError(null);

    try {
      const catalogApps = await fetchCatalog();
      setApps(catalogApps);
      setSelectedAppId((currentId) => {
        if (currentId && catalogApps.some((app) => app.id === currentId)) {
          return currentId;
        }
        return catalogApps[0]?.id ?? null;
      });
    } catch (error) {
      setCatalogError(error instanceof Error ? error.message : "Unknown catalog error");
    } finally {
      setCatalogLoading(false);
    }
  }, []);

  const catalogById = useMemo(() => {
    return new Map(apps.map((app) => [app.id, app]));
  }, [apps]);

  const sarefOptions = useMemo(() => {
    const types = Array.from(new Set(apps.map((app) => app.saref_type))).sort();
    return ["all", ...types];
  }, [apps]);

  const filteredApps = useMemo(() => {
    const lower = searchTerm.trim().toLowerCase();

    return apps.filter((app) => {
      const sarefMatch = sarefFilter === "all" || app.saref_type === sarefFilter;
      if (!sarefMatch) {
        return false;
      }

      if (!lower) {
        return true;
      }

      const haystack = [
        app.id,
        app.title,
        app.description,
        app.saref_type,
        app.publisher,
        ...app.tags,
      ]
        .join(" ")
        .toLowerCase();

      return haystack.includes(lower);
    });
  }, [apps, searchTerm, sarefFilter]);

  const selectedApp = useMemo(() => {
    if (!selectedAppId) {
      return null;
    }
    return apps.find((app) => app.id === selectedAppId) ?? null;
  }, [apps, selectedAppId]);

  const latestAssistantRecommendations = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant" && message.apps.length > 0) {
        return message.apps;
      }
    }
    return [] as RecommendedApp[];
  }, [messages]);

  const currentThinkingSteps = THINKING_STEPS[activeIntentHint];
  const currentThinkingStep = currentThinkingSteps[thinkingStepIndex % currentThinkingSteps.length];

  const stopActiveResponse = useCallback(() => {
    if (streamIntervalRef.current !== null) {
      window.clearInterval(streamIntervalRef.current);
      streamIntervalRef.current = null;
    }
    setStreamingMessageId(null);
    setActiveResponseStartedAt(null);
    setActiveResponseElapsedMs(0);
    setThinkingStepIndex(0);
  }, []);

  useEffect(() => {
    void loadCatalog();
  }, [loadCatalog]);

  useEffect(() => {
    if (activeResponseStartedAt === null) {
      return;
    }

    const interval = window.setInterval(() => {
      setActiveResponseElapsedMs(Date.now() - activeResponseStartedAt);
    }, 100);

    return () => {
      window.clearInterval(interval);
    };
  }, [activeResponseStartedAt]);

  useEffect(() => {
    if (!chatLoading) {
      return;
    }

      const interval = window.setInterval(() => {
      setThinkingStepIndex((prev) => prev + 1);
      }, 1800);

    return () => {
      window.clearInterval(interval);
    };
  }, [chatLoading]);

  useEffect(() => {
    return () => {
      if (streamIntervalRef.current !== null) {
        window.clearInterval(streamIntervalRef.current);
      }
    };
  }, []);

  const handleChatSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = chatInput.trim();
    if (!text || chatLoading || streamingMessageId) {
      return;
    }

    const startMs = Date.now();
    setMessages((prev) => [...prev, { id: generateMessageId(), role: "user", text, apps: [] }]);
    setChatInput("");
    setChatLoading(true);
    setActiveIntentHint(inferIntentHint(text));
    setThinkingStepIndex(0);
    setActiveResponseStartedAt(startMs);
    setActiveResponseElapsedMs(0);

    const assistantId = generateMessageId();

    try {
      const response = await fetch("/api/v1/chat/stream", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          session_id: sessionId ?? undefined,
          message: text,
        }),
      });

      if (!response.ok || !response.body) {
        throw new Error("Failed to reach chat service");
      }

      // Add empty assistant message for streaming
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "assistant",
          text: "",
          apps: [],
          isStreaming: true,
        },
      ]);
      setChatLoading(false);
      setStreamingMessageId(assistantId);

      // Parse SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let accumulatedText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          let evt: { type?: string; content?: string; apps?: RecommendedApp[]; session_id?: string };
          try {
            evt = JSON.parse(line.slice(6));
          } catch {
            continue;
          }

          if (evt.type === "apps") {
            const recommendedApps = normalizeRecommendedApps(evt.apps ?? []);
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, apps: recommendedApps } : m))
            );
            if (recommendedApps[0]?.app?.id) {
              setSelectedAppId(recommendedApps[0].app.id);
            }
          } else if (evt.type === "token") {
            accumulatedText += evt.content ?? "";
            const snapshot = accumulatedText;
            setMessages((prev) =>
              prev.map((m) => (m.id === assistantId ? { ...m, text: snapshot } : m))
            );
          } else if (evt.type === "done") {
            if (evt.session_id) {
              setSessionId(evt.session_id);
            }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, text: accumulatedText, isStreaming: false, responseTimeMs: Date.now() - startMs }
                  : m
              )
            );
            stopActiveResponse();
          } else if (evt.type === "error") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, text: evt.content ?? "An error occurred.", isStreaming: false, responseTimeMs: Date.now() - startMs }
                  : m
              )
            );
            stopActiveResponse();
          }
        }
      }

      // If stream ended without a "done" event, finalize
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.isStreaming
            ? { ...m, isStreaming: false, responseTimeMs: Date.now() - startMs }
            : m
        )
      );
      stopActiveResponse();
    } catch {
      // If we already added the assistant message, update it with error
      setMessages((prev) => {
        const hasAssistant = prev.some((m) => m.id === assistantId);
        if (hasAssistant) {
          return prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  text: "Chat service is currently unavailable. Please verify containers are healthy and retry.",
                  isStreaming: false,
                  responseTimeMs: Date.now() - startMs,
                }
              : m
          );
        }
        return [
          ...prev,
          {
            id: assistantId,
            role: "assistant" as const,
            text: "Chat service is currently unavailable. Please verify containers are healthy and retry.",
            apps: [],
            responseTimeMs: Date.now() - startMs,
          },
        ];
      });
      stopActiveResponse();
      setChatLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden px-4 py-6 font-body text-slate-100 sm:px-6 lg:px-10">
      <div className="pointer-events-none absolute -left-20 top-16 h-80 w-80 animate-glow rounded-full bg-cyan-400/25 blur-3xl" />
      <div className="pointer-events-none absolute bottom-0 right-10 h-96 w-96 animate-glow rounded-full bg-emerald-300/20 blur-3xl" />

      <header className="mx-auto mb-6 max-w-[1500px] rounded-3xl border border-white/10 bg-slate-900/70 p-6 shadow-aurora backdrop-blur-xl">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-cyan-300/40 bg-cyan-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-100">
              <Sparkles size={14} />
              Premium Validation Workspace
            </p>
            <h1 className="mt-3 font-display text-3xl font-semibold leading-tight text-white sm:text-4xl">
              HEDGE-ExpertAI Command Console
            </h1>
            <p className="mt-2 max-w-2xl text-slate-300">
              Review the entire app dataset in one place, query the chatbot, and verify recommendation quality without opening source files.
            </p>
          </div>
          <button
            type="button"
            onClick={() => {
              setSearchTerm("");
              setSarefFilter("all");
              void loadCatalog();
            }}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-600 bg-slate-800/80 px-4 py-2 text-sm font-medium text-slate-200 transition hover:border-cyan-300 hover:text-white"
          >
            <RefreshCw size={16} />
            Reload Catalog
          </button>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1500px] gap-6 lg:grid-cols-[1.12fr_1fr]">
        <section className="rounded-3xl border border-white/10 bg-slate-900/70 p-5 shadow-aurora backdrop-blur-xl">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-xl font-semibold text-white">App Catalog Explorer</h2>
              <p className="text-sm text-slate-400">Manual metadata review from the same source used by ingestion.</p>
            </div>
            <div className="inline-flex items-center gap-2 rounded-lg border border-emerald-300/30 bg-emerald-500/10 px-3 py-1 text-xs text-emerald-100">
              <Database size={14} />
              {apps.length} apps loaded
            </div>
          </div>

          <div className="mb-4 grid gap-3 md:grid-cols-[1fr_auto]">
            <label className="relative block">
              <Search size={16} className="pointer-events-none absolute left-3 top-3 text-slate-500" />
              <input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search by title, tag, publisher, or app ID"
                className="w-full rounded-xl border border-slate-700 bg-slate-950/70 py-2.5 pl-10 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-300 focus:outline-none"
              />
            </label>

            <select
              value={sarefFilter}
              onChange={(event) => setSarefFilter(event.target.value)}
              className="rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2.5 text-sm text-slate-100 focus:border-cyan-300 focus:outline-none"
            >
              {sarefOptions.map((option) => (
                <option key={option} value={option}>
                  {option === "all" ? "All SAREF Domains" : option}
                </option>
              ))}
            </select>
          </div>

          {catalogLoading ? (
            <div className="rounded-2xl border border-slate-700/70 bg-slate-900/50 p-8 text-center text-slate-300">
              Loading app catalog...
            </div>
          ) : null}

          {catalogError ? (
            <div className="mb-4 rounded-2xl border border-rose-300/40 bg-rose-500/10 p-4 text-sm text-rose-100">
              {catalogError}
            </div>
          ) : null}

          {!catalogLoading && !catalogError ? (
            <div className="grid min-h-[44rem] gap-4 xl:h-[62vh] xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
              <div className="custom-scroll min-h-0 space-y-3 overflow-y-auto pr-1">
                {filteredApps.map((app) => {
                  const selected = selectedAppId === app.id;
                  const recommended = latestAssistantRecommendations.some((item) => item.app.id === app.id);

                  return (
                    <button
                      key={app.id}
                      type="button"
                      onClick={() => setSelectedAppId(app.id)}
                      className={`w-full rounded-2xl border p-4 text-left transition ${
                        selected
                          ? "border-cyan-300 bg-cyan-500/10"
                          : "border-slate-700/80 bg-slate-900/50 hover:border-slate-500"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <p className="break-words font-display text-sm font-semibold text-white [overflow-wrap:anywhere]">{app.title}</p>
                        {recommended ? (
                          <span className="rounded-full border border-emerald-300/40 bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-200">
                            Recommended
                          </span>
                        ) : null}
                      </div>
                      <p className="mt-1 text-xs uppercase tracking-wider text-cyan-200/90">{app.id}</p>
                      <p className="mt-2 max-h-12 overflow-hidden text-sm text-slate-300">{app.description}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-200">{app.saref_type}</span>
                        <span className="rounded-full bg-slate-800 px-2.5 py-1 text-xs text-slate-300">v{app.version}</span>
                      </div>
                    </button>
                  );
                })}

                {filteredApps.length === 0 ? (
                  <div className="rounded-2xl border border-slate-700/80 bg-slate-900/50 p-4 text-sm text-slate-300">
                    No apps match your current filters.
                  </div>
                ) : null}
              </div>

              <div className="custom-scroll min-h-0 overflow-y-auto rounded-2xl border border-slate-700/80 bg-slate-900/60 p-4">
                {selectedApp ? (
                  <>
                    <h3 className="break-words font-display text-lg font-semibold text-white [overflow-wrap:anywhere]">{selectedApp.title}</h3>
                    <p className="mt-1 text-sm text-cyan-200">{selectedApp.id}</p>
                    <p className="mt-4 break-words text-sm leading-6 text-slate-200 [overflow-wrap:anywhere]">{selectedApp.description}</p>

                    <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                      <div className="rounded-xl border border-slate-700/70 bg-slate-950/60 p-3">
                        <p className="text-slate-400">Domain</p>
                        <p className="mt-1 text-slate-100">{selectedApp.saref_type}</p>
                      </div>
                      <div className="rounded-xl border border-slate-700/70 bg-slate-950/60 p-3">
                        <p className="text-slate-400">Publisher</p>
                        <p className="mt-1 break-words text-slate-100 [overflow-wrap:anywhere]">{selectedApp.publisher}</p>
                      </div>
                      <div className="rounded-xl border border-slate-700/70 bg-slate-950/60 p-3">
                        <p className="text-slate-400">Created</p>
                        <p className="mt-1 text-slate-100">{formatDate(selectedApp.created_at)}</p>
                      </div>
                      <div className="rounded-xl border border-slate-700/70 bg-slate-950/60 p-3">
                        <p className="text-slate-400">Updated</p>
                        <p className="mt-1 text-slate-100">{formatDate(selectedApp.updated_at)}</p>
                      </div>
                    </div>

                    <div className="mt-4">
                      <p className="text-xs uppercase tracking-wider text-slate-400">Tags</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {selectedApp.tags.map((tag) => (
                          <span
                            key={tag}
                            className="break-words rounded-full border border-slate-700 bg-slate-950/60 px-2.5 py-1 text-xs text-slate-200 [overflow-wrap:anywhere]"
                          >
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-xl border border-slate-700/70 bg-slate-950/60 p-3">
                        <p className="mb-2 text-xs uppercase tracking-wider text-slate-400">Input datasets</p>
                        <ul className="space-y-1 text-sm text-slate-200">
                          {selectedApp.input_datasets.map((dataset) => (
                            <li key={dataset} className="break-words [overflow-wrap:anywhere]">
                              • {dataset}
                            </li>
                          ))}
                        </ul>
                      </div>
                      <div className="rounded-xl border border-slate-700/70 bg-slate-950/60 p-3">
                        <p className="mb-2 text-xs uppercase tracking-wider text-slate-400">Output datasets</p>
                        <ul className="space-y-1 text-sm text-slate-200">
                          {selectedApp.output_datasets.map((dataset) => (
                            <li key={dataset} className="break-words [overflow-wrap:anywhere]">
                              • {dataset}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  </>
                ) : (
                  <p className="text-sm text-slate-300">Select an app to inspect full metadata.</p>
                )}
              </div>
            </div>
          ) : null}
        </section>

        <section className="rounded-3xl border border-white/10 bg-slate-900/70 p-5 shadow-aurora backdrop-blur-xl">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <h2 className="font-display text-xl font-semibold text-white">Chatbot Test Bench</h2>
              <p className="text-sm text-slate-400">Run prompts and verify recommendation IDs against the live catalog.</p>
            </div>
            <div className="rounded-lg border border-slate-700/80 bg-slate-950/60 px-3 py-1 text-xs text-slate-300">
              Session: {sessionId ?? "new"}
            </div>
          </div>

          <div className="custom-scroll mb-4 h-[44vh] space-y-3 overflow-y-auto rounded-2xl border border-slate-700/70 bg-slate-950/65 p-3">
            {messages.map((message) => (
              <motion.div
                key={message.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
                className={`rounded-2xl border p-3 ${
                  message.role === "user"
                    ? "ml-8 border-cyan-300/30 bg-cyan-500/10"
                    : "mr-8 border-slate-700/80 bg-slate-900/80"
                }`}
              >
                <div className="mb-2 flex items-center justify-between gap-2 text-xs uppercase tracking-wider text-slate-400">
                  <div className="inline-flex items-center gap-2">
                    {message.role === "assistant" ? <Bot size={13} /> : null}
                    {message.role}
                  </div>
                  {message.role === "assistant" ? (
                    <span className="rounded-full border border-slate-700/90 bg-slate-950/70 px-2 py-0.5 text-[11px] normal-case tracking-normal text-slate-300">
                      {message.isStreaming && activeResponseStartedAt !== null
                        ? formatDuration(activeResponseElapsedMs)
                        : formatDuration(message.responseTimeMs ?? 0)}
                    </span>
                  ) : null}
                </div>

                {message.role === "assistant" && !message.isStreaming ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} className="message-markdown text-sm text-slate-100">
                    {message.text}
                  </ReactMarkdown>
                ) : (
                  <p className="whitespace-pre-wrap text-sm leading-6 text-slate-100">{message.text}</p>
                )}

                {message.apps.length > 0 ? (
                  <div className="mt-3 space-y-2">
                    {message.apps.map((item) => {
                      const catalogHit = catalogById.has(item.app.id);
                      return (
                        <button
                          key={item.app.id}
                          type="button"
                          onClick={() => setSelectedAppId(item.app.id)}
                          className="w-full rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-left transition hover:border-cyan-300/60"
                        >
                          <div className="flex items-center justify-between gap-2">
                            <span className="font-display text-sm text-white">{item.app.title}</span>
                            <span className="text-xs text-cyan-200">score {item.score.toFixed(4)}</span>
                          </div>
                          <div className="mt-2 inline-flex items-center gap-1.5 text-xs">
                            {catalogHit ? (
                              <>
                                <CheckCircle2 size={14} className="text-emerald-300" />
                                <span className="text-emerald-200">Verified in catalog ({item.app.id})</span>
                              </>
                            ) : (
                              <>
                                <AlertCircle size={14} className="text-amber-300" />
                                <span className="text-amber-200">Not found in loaded catalog</span>
                              </>
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
              </motion.div>
            ))}

            {chatLoading ? (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
                className="mr-8 rounded-2xl border border-slate-700/80 bg-slate-900/80 p-3"
              >
                <div className="mb-2 flex items-center justify-between gap-2 text-xs uppercase tracking-wider text-slate-400">
                  <div className="inline-flex items-center gap-2">
                    <Bot size={13} />
                    assistant
                  </div>
                  <span className="rounded-full border border-cyan-300/40 bg-cyan-500/10 px-2 py-0.5 text-[11px] normal-case tracking-normal text-cyan-100">
                    {formatDuration(activeResponseElapsedMs)}
                  </span>
                </div>

                <div className="flex items-center gap-2 text-sm text-slate-200">
                  <div className="inline-flex items-center gap-1">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </div>
                  <span>Assistant is working...</span>
                </div>
                <p className="mt-2 text-sm text-slate-300">{currentThinkingStep}</p>
              </motion.div>
            ) : null}
          </div>

          <form onSubmit={handleChatSubmit} className="space-y-3">
            <textarea
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Try: Find apps for flood warning and water quality monitoring"
              className="h-28 w-full resize-none rounded-2xl border border-slate-700 bg-slate-950/70 p-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-cyan-300 focus:outline-none"
            />
            <button
              type="submit"
              disabled={chatLoading || streamingMessageId !== null}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-cyan-300/50 bg-cyan-500/20 px-4 py-2.5 text-sm font-semibold text-cyan-50 transition hover:bg-cyan-500/30 disabled:cursor-not-allowed disabled:opacity-70"
            >
              <SendHorizontal size={16} />
              {chatLoading
                ? "Assistant is thinking..."
                : streamingMessageId
                  ? "Assistant is typing..."
                  : "Send to HEDGE-ExpertAI"}
            </button>
          </form>
        </section>
      </main>
    </div>
  );
}
