"use client";

import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Brand } from "@/components/SiteHeader";
import { saveAnalysis } from "@/lib/browser-analysis-store";
import type { AnalyzeResponse } from "@/lib/nadid-types";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  function validateFile(nextFile: File) {
    if (!nextFile.name.toLowerCase().endsWith(".docx")) {
      setError("النسخة الحالية تقبل ملفات Word بصيغة DOCX فقط.");
      return false;
    }

    if (nextFile.size > 25 * 1024 * 1024) {
      setError("الحد التجريبي الحالي للرفع هو 25 ميجابايت.");
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

  async function analyzeFile() {
    if (!file || isLoading) return;

    setIsLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData
      });

      const payload = await response.json();

      if (!response.ok) {
        throw new Error(payload.error || "تعذر تحليل المستند.");
      }

      const analysis = payload as AnalyzeResponse;
      await saveAnalysis(analysis);
      router.push(`/editor?id=${analysis.document.id}`);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "حدث خطأ أثناء قراءة المستند."
      );
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
            accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
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
                  {isLoading ? "نقرأ المستند الآن…" : "ابدأ المراجعة"}
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
            <span>يبقى الأصل على جهازك في هذه النسخة التجريبية</span>
            <span>حتى 25 MB حاليًا</span>
          </div>
        </div>
      </section>
    </main>
  );
}
