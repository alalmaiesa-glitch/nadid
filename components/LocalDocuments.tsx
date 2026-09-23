"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listAnalyses } from "@/lib/browser-analysis-store";
import type { AnalyzeResponse } from "@/lib/nadid-types";

export default function LocalDocuments() {
  const [documents, setDocuments] = useState<AnalyzeResponse[] | null>(null);

  useEffect(() => {
    listAnalyses()
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, []);

  if (documents === null) {
    return <div className="documents-loading">نقرأ المستندات المحلية…</div>;
  }

  if (documents.length === 0) {
    return (
      <div className="documents-empty">
        <h2>لا توجد مستندات بعد</h2>
        <p>
          ارفع أول ملف DOCX ليظهر هنا أثناء التطوير المحلي.
        </p>
        <Link href="/upload" className="button button-primary">
          رفع مستند
        </Link>
      </div>
    );
  }

  return (
    <div className="documents-grid">
      {documents.map((item) => (
        <article className="document-card" key={item.document.id}>
          <div className="document-card-head">
            <span className="document-file-icon">و</span>
            <span className="status-badge status-local">محلي</span>
          </div>
          <h2>{item.document.filename}</h2>
          <p>
            {item.document.wordCount.toLocaleString("ar-SA")} كلمة ·{" "}
            {item.document.paragraphCount.toLocaleString("ar-SA")} فقرة
          </p>
          <div className="document-card-footer">
            <span>{item.suggestions.length} ملاحظة</span>
            <Link href={`/editor?id=${item.document.id}`}>
              فتح المستند
            </Link>
          </div>
        </article>
      ))}
    </div>
  );
}
