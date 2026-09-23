"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Brand } from "@/components/SiteHeader";
import { saveAnalysis } from "@/lib/browser-analysis-store";
import { getSupabaseBrowser } from "@/lib/supabase-browser";
import { uploadResumable } from "@/lib/resumable-upload";
import type { AnalyzeResponse } from "@/lib/nadid-types";

const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function wait(milliseconds: number) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [progressLabel, setProgressLabel] = useState("");
  const [error, setError] = useState("");

  const persistentMode = Boolean(getSupabaseBrowser());
  const maxBytes = persistentMode
    ? 100 * 1024 * 1024
    : 25 * 1024 * 1024;

  function validateFile(nextFile: File) {
    if (!nextFile.name.toLowerCase().endsWith(".docx")) {
      setError("النسخة الحالية تقبل ملفات Word بصيغة DOCX فقط.");
      return false;
    }

    if (nextFile.size > maxBytes) {
      setError(
        persistentMode
          ? "الحد التشغيلي الحالي للرفع هو 100 ميجابايت."
          : "الحد التجريبي المحلي الحالي هو 25 ميجابايت."
      );
      return false;
    }

    setError("");
    setFile(nextFile);
    return true;
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextFile = event.target.files?.[0];
    if (nextFile) validateFile(nextFile);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setIsDragging(false);
    const nextFile = event.dataTransfer.files?.[0];
    if (nextFile) validateFile(nextFile);
  }

  async function analyzeLocally(nextFile: File) {
    setProgressLabel("نقرأ المستند الآن…");

    const formData = new FormData();
    formData.append("file", nextFile);

    const response = await fetch("/api/analyze", {
      method: "POST",
      body: formData
    });

    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.error || "تعذر تحليل المستند.");
    }

    return payload as AnalyzeResponse;
  }

  async function uploadPersistently(nextFile: File) {
    const supabase = getSupabaseBrowser();

    if (!supabase) {
      return analyzeLocally(nextFile);
    }

    setProgressLabel("نجهز مساحة المستند…");

    const createResponse = await fetch("/api/uploads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filename: nextFile.name,
        size: nextFile.size
      })
    });

    const upload = await createResponse.json();

    if (!createResponse.ok) {
      throw new Error(
        upload.error || "تعذر تجهيز مساحة رفع المستند."
      );
    }

    if (nextFile.size > 6 * 1024 * 1024) {
      setProgressLabel("نرفع الملف على أجزاء قابلة للاستئناف… 0%");

      await uploadResumable({
        file: nextFile,
        storagePath: upload.storagePath,
        signedToken: upload.token,
        onProgress(percentage) {
          setProgressLabel(
            `نرفع الملف على أجزاء قابلة للاستئناف… ${percentage}%`
          );
        }
      });
    } else {
      setProgressLabel("نرفع الملف مباشرة إلى التخزين الآمن…");

      const { error: uploadError } = await supabase.storage
        .from("nadid-documents")
        .uploadToSignedUrl(
          upload.storagePath,
          upload.token,
          nextFile,
          {
            contentType: nextFile.type || DOCX_MIME
          }
        );

      if (uploadError) {
        throw new Error("تعذر رفع الملف إلى التخزين.");
      }
    }

    setProgressLabel("نضع المستند في قائمة المعالجة الآمنة…");

    const finalizeResponse = await fetch(
      `/api/documents/${upload.documentId}/finalize-upload`,
      { method: "POST" }
    );

    const queued = await finalizeResponse.json();

    if (!finalizeResponse.ok) {
      throw new Error(
        queued.error || "تعذر إدخال المستند في قائمة المعالجة."
      );
    }

    const deadline = Date.now() + 10 * 60 * 1000;

    while (Date.now() < deadline) {
      const statusResponse = await fetch(
        `/api/documents/${upload.documentId}/status`,
        { cache: "no-store" }
      );

      if (!statusResponse.ok) {
        throw new Error("تعذر متابعة حالة معالجة المستند.");
      }

      const status = await statusResponse.json();

      if (status.documentStatus === "failed" || status.queueState === "failed") {
        throw new Error(
          status.queueError || "تعذرت معالجة المستند بعد عدة محاولات."
        );
      }

      if (
        status.versionNo &&
        (status.documentStatus === "partial_ready" ||
          status.documentStatus === "ready")
      ) {
        const documentResponse = await fetch(
          `/api/documents/${upload.documentId}`,
          { cache: "no-store" }
        );

        if (!documentResponse.ok) {
          throw new Error("اكتملت المعالجة لكن تعذر تحميل المستند.");
        }

        return (await documentResponse.json()) as AnalyzeResponse;
      }

      if (status.queueState === "processing") {
        setProgressLabel(
          `نراجع المستند الآن… المحاولة ${status.queueAttempts || 1}`
        );
      } else {
        setProgressLabel("المستند في قائمة المعالجة…");
      }

      await wait(1500);
    }

    throw new Error(
      "المستند ما زال قيد المعالجة. ستجده في «مستنداتي» عند اكتماله."
    );
  }

  async function analyzeFile() {
    if (!file || isLoading) return;

    setIsLoading(true);
    setError("");

    try {
      const analysis = persistentMode
        ? await uploadPersistently(file)
        : await analyzeLocally(file);

      await saveAnalysis(analysis);
      setProgressLabel("اكتملت المراجعة الأولى.");
      router.push(`/editor?id=${analysis.document.id}`);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "حدث خطأ أثناء قراءة المستند."
      );
      setProgressLabel("");
      setIsLoading(false);
    }
  }

  return (
    <main className="app-page">
      <header className="app-topbar">
        <div className="shell">
          <Brand />
          <span className="app-topbar-title">مستند جديد</span>
        </div>
      </header>

      <section className="upload-wrap">
        <div className="upload-heading">
          <h1>ارفع مستندك كاملًا</h1>
          <p>نَضِيد يتولى قراءة البنية والتقسيم والمراجعة دون أن تفقد السياق.</p>
        </div>

        <div
          className={`dropzone ${isDragging ? "dropzone-active" : ""}`}
          onDragEnter={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setIsDragging(false)}
          onDrop={onDrop}
        >
          <input
            ref={inputRef}
            type="file"
            accept={`.docx,${DOCX_MIME}`}
            onChange={onFileChange}
            hidden
          />

          <div className="upload-icon" aria-hidden="true">
            {isLoading ? "…" : "↑"}
          </div>

          {file ? (
            <>
              <h2>{file.name}</h2>
              <p>
                {(file.size / 1024 / 1024).toFixed(2)} ميجابايت · جاهز للفحص
              </p>
              <div className="upload-actions">
                <button
                  className="button button-primary"
                  onClick={analyzeFile}
                  disabled={isLoading}
                >
                  {isLoading
                    ? progressLabel || "نجهز المستند…"
                    : "ابدأ المراجعة"}
                </button>
                {!isLoading && (
                  <button
                    className="button button-secondary"
                    onClick={() => inputRef.current?.click()}
                  >
                    تغيير الملف
                  </button>
                )}
              </div>
            </>
          ) : (
            <>
              <h2>اسحب ملف Word إلى هنا</h2>
              <p>أو اختر الملف من جهازك لبدء المراجعة.</p>
              <button
                className="button button-primary"
                onClick={() => inputRef.current?.click()}
              >
                اختيار ملف DOCX
              </button>
            </>
          )}

          {error && <div className="upload-error">{error}</div>}

          <div className="upload-meta">
            <span>DOCX</span>
            <span>
              {persistentMode
                ? "يرفع مباشرة إلى التخزين دون المرور عبر خادم الواجهة"
                : "وضع تطوير محلي"}
            </span>
            <span>
              حتى {persistentMode ? "100" : "25"} MB حاليًا
            </span>
          </div>
        </div>
      </section>
    </main>
  );
}
