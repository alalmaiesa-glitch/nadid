import Link from "next/link";
import { redirect } from "next/navigation";
import { Brand } from "@/components/SiteHeader";
import LocalDocuments from "@/components/LocalDocuments";
import { listUserDocuments } from "@/lib/server/document-persistence";
import {
  getCurrentUser,
  isSupabaseConfigured
} from "@/lib/supabase-server";

function statusLabel(status: string) {
  switch (status) {
    case "ready":
      return "جاهز";
    case "partial_ready":
      return "جاهز للمراجعة";
    case "processing":
      return "قيد المعالجة";
    case "failed":
      return "تعذر الإكمال";
    default:
      return "قيد التجهيز";
  }
}

function statusClass(status: string) {
  if (status === "ready") return "status-ready";
  if (status === "failed") return "status-failed";
  if (status === "processing") return "status-processing";
  return "status-partial";
}

export default async function DocumentsPage() {
  const configured = isSupabaseConfigured();
  const user = configured ? await getCurrentUser() : null;

  if (configured && !user) {
    redirect("/login?next=/documents");
  }

  const documents = user
    ? await listUserDocuments(user.id)
    : [];

  return (
    <main className="documents-page">
      <header className="dashboard-header">
        <div className="shell dashboard-header-inner">
          <Brand />
          <div className="dashboard-user">
            {user?.email && <span>{user.email}</span>}
            {user && (
              <form action="/auth/signout" method="post">
                <button className="text-button">تسجيل الخروج</button>
              </form>
            )}
          </div>
        </div>
      </header>

      <section className="shell documents-content">
        <div className="documents-title-row">
          <div>
            <span className="eyebrow">مساحة العمل</span>
            <h1>مستنداتي</h1>
            <p>
              راجع مستنداتك، تابع حالة المعالجة، وافتح أي نسخة للمتابعة.
            </p>
          </div>

          <Link href="/upload" className="button button-primary">
            مستند جديد
          </Link>
        </div>

        {!configured ? (
          <>
            <div className="local-mode-banner">
              تعمل هذه البيئة حاليًا بوضع التطوير المحلي. عند ربط Supabase،
              ستظهر مستندات الحساب ونسخها هنا من التخزين الدائم.
            </div>
            <LocalDocuments />
          </>
        ) : documents.length === 0 ? (
          <div className="documents-empty">
            <h2>ابدأ بأول مستند</h2>
            <p>
              لم ترفع أي مستند إلى حسابك بعد. ارفع ملف Word كاملًا وسيبدأ
              نَضِيد بالفحص السريع ثم المراجعة العميقة.
            </p>
            <Link href="/upload" className="button button-primary">
              رفع مستند
            </Link>
          </div>
        ) : (
          <div className="documents-grid">
            {documents.map((document) => (
              <article className="document-card" key={document.id}>
                <div className="document-card-head">
                  <span className="document-file-icon">و</span>
                  <span
                    className={
                      "status-badge " + statusClass(document.status)
                    }
                  >
                    {statusLabel(document.status)}
                  </span>
                </div>

                <h2>{document.title}</h2>
                <p className="document-filename">{document.filename}</p>

                <div className="document-stats">
                  <span>
                    {document.wordCount.toLocaleString("ar-SA")} كلمة
                  </span>
                  <span>
                    {document.paragraphCount.toLocaleString("ar-SA")} فقرة
                  </span>
                  <span>v{document.versionNo}</span>
                </div>

                <div className="document-card-footer">
                  <span>
                    آخر تحديث{" "}
                    {new Intl.DateTimeFormat("ar-SA", {
                      dateStyle: "medium"
                    }).format(new Date(document.updatedAt))}
                  </span>
                  <Link href={`/editor?id=${document.id}`}>
                    فتح المستند
                  </Link>
                </div>
              </article>
            ))}
          </div>
        )}
      </section>
    </main>
  );
}
