import Link from "next/link";
import { Brand } from "@/components/SiteHeader";

export default function UploadPage() {
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

        <div className="dropzone">
          <div className="upload-icon" aria-hidden="true">↑</div>
          <h2>اسحب ملف Word إلى هنا</h2>
          <p>أو اختر الملف من جهازك لبدء المراجعة.</p>
          <Link href="/editor" className="button button-primary">
            اختيار ملف DOCX
          </Link>
          <div className="upload-meta">
            <span>DOCX</span>
            <span>يبقى الأصل محفوظًا</span>
            <span>لا تقسيم يدوي</span>
          </div>
        </div>
      </section>
    </main>
  );
}
