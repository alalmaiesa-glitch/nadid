import Link from "next/link";

export function Brand() {
  return (
    <Link href="/" className="brand" aria-label="نَضِيد - الصفحة الرئيسية">
      <span className="brand-mark" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
      <span className="brand-copy">
        <strong>نَضِيد</strong>
        <small>محرر العربية الذكي</small>
      </span>
    </Link>
  );
}

export default function SiteHeader() {
  return (
    <header className="site-header">
      <div className="shell header-inner">
        <Brand />
        <nav className="main-nav" aria-label="التنقل الرئيسي">
          <Link href="/#capabilities">المزايا</Link>
          <Link href="/#how">كيف يعمل؟</Link>
          <Link href="/documents">مستنداتي</Link>
        </nav>
        <div className="header-actions">
          <Link href="/login" className="text-button">تسجيل الدخول</Link>
          <Link href="/upload" className="button button-small button-primary">
            ابدأ المراجعة
          </Link>
        </div>
      </div>
    </header>
  );
}
