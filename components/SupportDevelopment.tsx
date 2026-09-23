"use client";

import { useState } from "react";

const presets = [5, 10];

export default function SupportDevelopment() {
  const [selected, setSelected] = useState<number | "custom">(5);
  const [customAmount, setCustomAmount] = useState("");

  function continueToSupport() {
    const amount = selected === "custom" ? Number(customAmount) : selected;

    if (!Number.isFinite(amount) || amount <= 0) return;

    const query = new URLSearchParams({
      amount: String(amount),
      currency: "USD",
      type: "support"
    });

    window.location.href = "/support?" + query.toString();
  }

  return (
    <section className="support-section" id="support">
      <div className="shell">
        <div className="support-card">
          <div className="support-copy">
            <span className="eyebrow">ساهم في استمرار التطوير</span>
            <h2>استفدت من نَضِيد؟ ادعمنا لنكمل التطوير.</h2>
            <p>
              مساهمتك اختيارية، وتساعدنا على تحسين دقة المراجعة، وتوسيع دعم
              المستندات، وتطوير مزايا جديدة لنَضِيد.
            </p>
            <small>
              المساهمة لا تمنح مزايا مدفوعة بحد ذاتها، وستبقى الخدمات المدفوعة
              لاحقًا منفصلة وواضحة.
            </small>
          </div>

          <div className="support-options">
            <div className="support-amounts">
              {presets.map((amount) => (
                <button
                  key={amount}
                  type="button"
                  className={"support-amount " + (selected === amount ? "active" : "")}
                  onClick={() => setSelected(amount)}
                >
                  ${amount}
                </button>
              ))}

              <button
                type="button"
                className={"support-amount " + (selected === "custom" ? "active" : "")}
                onClick={() => setSelected("custom")}
              >
                مبلغ آخر
              </button>
            </div>

            {selected === "custom" && (
              <div className="support-custom">
                <label htmlFor="support-amount">المبلغ بالدولار</label>
                <div className="support-input-wrap">
                  <span>$</span>
                  <input
                    id="support-amount"
                    type="number"
                    min="1"
                    step="1"
                    inputMode="decimal"
                    value={customAmount}
                    onChange={(event) => setCustomAmount(event.target.value)}
                    placeholder="25"
                  />
                </div>
              </div>
            )}

            <button
              type="button"
              className="button button-primary support-submit"
              onClick={continueToSupport}
            >
              ادعم تطوير نَضِيد
            </button>

            <span className="support-note">
              دفع آمن — سيتم تفعيل بوابة الدفع عند ربط الحساب التجاري.
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}