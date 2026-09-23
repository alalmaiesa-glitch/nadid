"use client";

import Link from "next/link";
import { ReactNode, useEffect, useMemo, useState } from "react";
import { Brand } from "@/components/SiteHeader";
import { getAnalysis } from "@/lib/browser-analysis-store";
import type {
  AnalyzeResponse,
  DeepMemorySnapshot,
  DocumentBlock,
  QuickSuggestion,
  ReviewCategory
} from "@/lib/nadid-types";

const categoryLabels: Record<ReviewCategory | "all", string> = {
  all: "الكل",
  language: "لغة",
  style: "صياغة",
  consistency: "اتساق",
  protection: "حماية"
};

type DeepState = "idle" | "loading" | "ready" | "unavailable" | "failed";

function highlightSuggestion(
  block: DocumentBlock,
  suggestion?: QuickSuggestion
): ReactNode {
  if (!suggestion || !block.text.includes(suggestion.original)) {
    return block.text;
  }

  const index = block.text.indexOf(suggestion.original);
  const before = block.text.slice(0, index);
  const after = block.text.slice(index + suggestion.original.length);

  return (
    <>
      {before}
      <span
        className={
          suggestion.category === "language" ? "mark-grammar" : "mark-style"
        }
      >
        {suggestion.original}
      </span>
      {after}
    </>
  );
}

export default function EditorPage() {
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const [blocks, setBlocks] = useState<DocumentBlock[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] =
    useState<ReviewCategory | "all">("all");
  const [accepted, setAccepted] = useState<Set<string>>(new Set());
  const [rejected, setRejected] = useState<Set<string>>(new Set());
  const [visibleCount, setVisibleCount] = useState(80);
  const [validationMessage, setValidationMessage] = useState("");
  const [deepState, setDeepState] = useState<DeepState>("idle");
  const [deepMemory, setDeepMemory] = useState<DeepMemorySnapshot | null>(null);
  const [documentId, setDocumentId] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [savingDecision, setSavingDecision] = useState(false);

  useEffect(() => {
    async function loadDocument(id: string) {
      let stored: AnalyzeResponse | null | undefined;

      try {
        const response = await fetch(`/api/documents/${id}`, {
          cache: "no-store"
        });

        if (response.ok) {
          stored = (await response.json()) as AnalyzeResponse;
        }
      } catch {
        stored = null;
      }

      if (!stored) {
        stored = await getAnalysis(id);
      }

      if (stored) {
        setAnalysis(stored);
        setBlocks(stored.document.blocks);
      }

      return stored ?? null;
    }

    async function refreshPersistentDocument(id: string) {
      try {
        const response = await fetch(`/api/documents/${id}`, {
          cache: "no-store"
        });

        if (!response.ok) return;

        const updated = (await response.json()) as AnalyzeResponse;
        setAnalysis(updated);
      } catch {
        // Keep the current document available even if refresh fails.
      }
    }

    async function loadDeepReview(id: string) {
      setDeepState("loading");

      try {
        let response = await fetch(`/api/documents/${id}/deep-review`, {
          cache: "no-store"
        });

        if (response.status === 404) {
          response = await fetch(`/api/documents/${id}/deep-review`, {
            method: "POST"
          });
        }

        if (response.status === 409 || response.status === 404) {
          setDeepState("unavailable");
          return;
        }

        if (!response.ok) {
          setDeepState("failed");
          return;
        }

        const payload = await response.json();
        setDeepMemory(payload.memory as DeepMemorySnapshot);
        setDeepState("ready");
        await refreshPersistentDocument(id);
      } catch {
        setDeepState("failed");
      }
    }

    async function load() {
      const id = new URLSearchParams(window.location.search).get("id");

      if (!id) {
        setLoading(false);
        return;
      }

      setDocumentId(id);
      const stored = await loadDocument(id);
      setLoading(false);

      if (stored) {
        void loadDeepReview(id);
      }
    }

    load().catch(() => setLoading(false));
  }, []);

  const pendingSuggestions = useMemo(() => {
    if (!analysis) return [];

    return analysis.suggestions.filter(
      (item) =>
        !accepted.has(item.id) &&
        !rejected.has(item.id) &&
        (activeCategory === "all" || item.category === activeCategory)
    );
  }, [analysis, accepted, rejected, activeCategory]);

  const suggestionsByBlock = useMemo(() => {
    const map = new Map<string, QuickSuggestion>();
    if (!analysis) return map;

    for (const item of analysis.suggestions) {
      if (accepted.has(item.id) || rejected.has(item.id)) continue;
      if (!map.has(item.blockId) && item.replacement) {
        map.set(item.blockId, item);
      }
    }
    return map;
  }, [analysis, accepted, rejected]);

  const outline = useMemo(() => {
    const headings = blocks.filter((block) => block.type === "heading");

    if (headings.length > 0) {
      return headings.slice(0, 24);
    }

    return blocks.slice(0, 12).map((block) => ({
      ...block,
      text:
        block.text.length > 45
          ? block.text.slice(0, 45) + "…"
          : block.text
    }));
  }, [blocks]);

  async function acceptSuggestion(item: QuickSuggestion) {
    if (!analysis || !item.replacement) return;

    const block = blocks.find((entry) => entry.id === item.blockId);
    if (!block) return;

    const protectedFacts = analysis.protectedFacts.filter(
      (fact) => fact.blockId === block.id
    );

    const response = await fetch("/api/validate-patch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        blockText: block.text,
        original: item.original,
        replacement: item.replacement,
        protectedFacts
      })
    });

    const result = await response.json();

    if (result.status !== "PASS") {
      setValidationMessage(
        "أوقف نَضِيد هذا التعديل لأنه قد يغيّر معلومة محمية في النص."
      );
      return;
    }

    setSavingDecision(true);

    try {
      await fetch(`/api/suggestions/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "accepted" })
      });

      setBlocks((current) =>
        current.map((entry) =>
          entry.id === block.id
            ? { ...entry, text: result.candidate }
            : entry
        )
      );

      setAccepted((current) => {
        const next = new Set(current);
        next.add(item.id);
        return next;
      });

      setValidationMessage("تم تطبيق التعديل بعد اجتياز فحص حماية المعنى.");
    } finally {
      setSavingDecision(false);
    }
  }

  async function rejectSuggestion(item: QuickSuggestion) {
    setRejected((current) => {
      const next = new Set(current);
      next.add(item.id);
      return next;
    });

    setSavingDecision(true);

    try {
      await fetch(`/api/suggestions/${item.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "rejected" })
      });

      setValidationMessage("تم تجاهل الملاحظة ولن تُطبق على النص.");
    } finally {
      setSavingDecision(false);
    }
  }

  async function exportDocument() {
    if (!documentId || exporting || savingDecision) return;

    setExporting(true);
    setValidationMessage("نُنشئ نسخة جديدة من التعديلات المقبولة…");

    try {
      const response = await fetch(
        `/api/documents/${documentId}/versions`,
        { method: "POST" }
      );

      const payload = await response.json();

      if (!response.ok) {
        if (payload.code === "NO_ACCEPTED_PATCHES") {
          setValidationMessage(
            "لا توجد تعديلات مقبولة بعد لإنشاء نسخة جديدة."
          );
        } else if (payload.code === "VERSION_CHANGED") {
          setValidationMessage(
            "ظهرت نسخة أحدث من المستند. أعد تحميل الصفحة قبل التصدير."
          );
        } else {
          setValidationMessage(
            "تعذر إنشاء النسخة الجديدة. تأكد من تفعيل التخزين ومحرك AEE."
          );
        }
        return;
      }

      const download = await fetch(payload.downloadUrl);
      if (!download.ok) {
        throw new Error("download_failed");
      }

      const blob = await download.blob();
      const url = URL.createObjectURL(blob);
      const link = window.document.createElement("a");
      link.href = url;
      link.download =
        analysis?.document.filename.replace(/\.docx$/i, "") +
        `-nadid-v${payload.versionNo}.docx`;
      window.document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);

      setValidationMessage(
        `تم إنشاء النسخة ${payload.versionNo} وتنزيلها بنجاح.`
      );

      window.location.assign(
        `/editor?id=${encodeURIComponent(documentId)}`
      );
    } catch {
      setValidationMessage(
        "حدث خطأ أثناء إنشاء ملف Word الجديد."
      );
    } finally {
      setExporting(false);
    }
  }

  if (loading) {
    return (
      <main className="editor-empty">
        <div className="loading-ring" />
        <h1>نفتح المستند…</h1>
        <p>نجهز النص والملاحظات الأولى.</p>
      </main>
    );
  }

  if (!analysis) {
    return (
      <main className="editor-empty">
        <Brand />
        <h1>لا يوجد مستند مفتوح</h1>
        <p>ارفع ملف DOCX أولًا ليظهر هنا مع نتائج المراجعة.</p>
        <Link href="/upload" className="button button-primary">
          رفع مستند
        </Link>
      </main>
    );
  }

  const visibleBlocks = blocks.slice(0, visibleCount);
  const totalSuggestions =
    analysis.suggestions.length - accepted.size - rejected.size;

  const deepStatusLabel =
    deepState === "ready"
      ? "● ذاكرة المستند مكتملة"
      : deepState === "loading"
        ? "المراجعة العميقة تعمل…"
        : deepState === "failed"
          ? "تعذر إكمال المراجعة العميقة"
          : deepState === "unavailable"
            ? "المراجعة العميقة غير مفعلة"
            : "الفحص السريع مكتمل";

  return (
    <main className="editor-app">
      <header className="editor-header">
        <Brand />
        <span className="editor-doc-title">
          {analysis.document.filename}
          {analysis.document.versionNo
            ? ` · v${analysis.document.versionNo}`
            : ""}
        </span>
        <div className="editor-header-actions">
          <Link
            href="/upload"
            className="button button-small button-secondary"
          >
            مستند جديد
          </Link>
          <button
            className="button button-small button-primary"
            onClick={exportDocument}
            disabled={exporting || savingDecision}
          >
            {exporting ? "نُنشئ النسخة…" : "تصدير"}
          </button>
        </div>
      </header>

      <div className="editor-layout">
        <aside className="outline-panel">
          <div className="panel-head">
            <h3>هيكل المستند</h3>
            <span className="panel-count">{outline.length}</span>
          </div>
          <div className="outline-content">
            {outline.map((block, index) => (
              <div
                className={"outline-item " + (index === 0 ? "active" : "")}
                key={block.id}
              >
                <span>•</span>
                {block.text}
              </div>
            ))}
          </div>
        </aside>

        <section className="document-stage">
          <article className="document-sheet">
            {visibleBlocks.map((block, index) =>
              block.type === "heading" ? (
                index === 0 ? (
                  <h1 key={block.id}>{block.text}</h1>
                ) : (
                  <h2 key={block.id}>{block.text}</h2>
                )
              ) : (
                <p key={block.id}>
                  {highlightSuggestion(
                    block,
                    suggestionsByBlock.get(block.id)
                  )}
                </p>
              )
            )}

            {visibleCount < blocks.length && (
              <button
                className="button button-secondary load-more"
                onClick={() =>
                  setVisibleCount((current) =>
                    Math.min(current + 80, blocks.length)
                  )
                }
              >
                عرض المزيد من المستند
              </button>
            )}
          </article>
        </section>

        <aside className="review-panel">
          <div className="panel-head">
            <h3>المراجعة</h3>
            <span className="panel-count">{totalSuggestions}</span>
          </div>

          <div className="review-tabs review-tabs-five">
            {(
              ["all", "language", "style", "consistency", "protection"] as const
            ).map((category) => (
              <button
                className={
                  "review-tab " +
                  (activeCategory === category ? "active" : "")
                }
                key={category}
                onClick={() => setActiveCategory(category)}
              >
                {categoryLabels[category]}
              </button>
            ))}
          </div>

          {validationMessage && (
            <div className="validation-message">{validationMessage}</div>
          )}

          <div className="review-list">
            {pendingSuggestions.length === 0 ? (
              <div className="review-empty">
                لا توجد ملاحظات في هذا التصنيف ضمن نتائج المراجعة الحالية.
              </div>
            ) : (
              pendingSuggestions.map((item) => (
                <article className="review-card" key={item.id}>
                  <span className="review-card-type">
                    {categoryLabels[item.category]} · ثقة{" "}
                    {Math.round(item.confidence * 100)}%
                  </span>
                  <h4>{item.title}</h4>
                  <p>{item.explanation}</p>

                  {item.replacement && (
                    <div className="review-diff">
                      <div className="old-text">{item.original}</div>
                      <div className="new-text">{item.replacement}</div>
                    </div>
                  )}

                  <div className="review-actions">
                    {item.replacement && (
                      <button
                        className="accept"
                        onClick={() => acceptSuggestion(item)}
                      >
                        قبول
                      </button>
                    )}
                    <button onClick={() => rejectSuggestion(item)}>
                      تجاهل
                    </button>
                  </div>
                </article>
              ))
            )}

            {analysis.protectedFacts.slice(0, 12).map((fact) => (
              <article className="review-card protected-card" key={fact.id}>
                <span className="review-card-type">حماية معنى</span>
                <h4>{fact.value}</h4>
                <p>
                  رصد نَضِيد هذه القيمة كعنصر محمي ويختبر التعديلات حولها قبل
                  تطبيقها.
                </p>
              </article>
            ))}
          </div>
        </aside>
      </div>

      <div className="editor-statusbar">
        <span className={deepState === "ready" ? "status-good" : ""}>
          {deepStatusLabel}
        </span>
        {analysis.document.versionNo && (
          <span>النسخة {analysis.document.versionNo}</span>
        )}
        <span>{analysis.document.wordCount.toLocaleString("ar-SA")} كلمة</span>
        <span>{totalSuggestions} ملاحظة</span>
        <span>{analysis.protectedFacts.length} قيمة محمية</span>
        {deepMemory && <span>{deepMemory.facts.length} حقيقة</span>}
        {deepMemory && deepMemory.conflicts.length > 0 && (
          <span>{deepMemory.conflicts.length} تعارض محتمل</span>
        )}
      </div>
    </main>
  );
}
