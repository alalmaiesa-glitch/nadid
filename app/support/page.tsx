"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Brand } from "@/components/SiteHeader";

export default function SupportPage() {
  const params = useSearchParams();
  const raw = Number(params.get("amount") ?? "5");
  const amount = Number.isFinite(raw) && raw > 0 ? raw : 5;

  return (
    <main className="support-page">
      <header className="app-topbar">
        <div className="shell">
          <Brand />
          <span className="app-topbar-title">دعم تطوير نَضِيد</span>
        </div>
      </header>

      <section className="support-checkout">
        <div className="support-checkout-card">
          <span className="eyebrow">مساهمة اختيارية</span>
          <h1>شكرًا لدعمك تطوير نَضِيد.</h1>
          <p>
            اخترت مساهمة بقيمة <strong>${amount}</strong>. ستستخدم هذه
            المساهمة في استضافة الخدمة، وتحسين المحرك، وتطوير مزايا جديدة.
          </p>

          <div className="support-summary">
            <span>دعم تطوير نَضِيد</span>
            <strong>${amount}</strong>
          </div>

          <div className="payment-placeholder">
            <strong>بوابة الدفع</strong>
            <p>
              سيظهر نموذج الدفع الآمن هنا فور ربط حساب Moyasar وإضافة مفاتيح
              الاختبار ثم الإنتاج.
            </p>
          </div>

          <div className="support-checkout-actions">
            <Link href="/#support" className="button button-secondary">
              تعديل المبلغ
            </Link>
            <button className="button button-primary" disabled>
              متابعة الدفع
            </button>
          </div>

          <small>
            لا تدخل بيانات بطاقة في هذه النسخة قبل تفعيل بوابة الدفع الرسمية.
          </small>
        </div>
      </section>
    </main>
  );
}