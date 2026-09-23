"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import { Brand } from "@/components/SiteHeader";
import { getSupabaseBrowser } from "@/lib/supabase-browser";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<
    "idle" | "sending" | "sent" | "error" | "unavailable"
  >("idle");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const supabase = getSupabaseBrowser();
    if (!supabase) {
      setState("unavailable");
      return;
    }

    setState("sending");

    const next =
      new URLSearchParams(window.location.search).get("next") ??
      "/documents";

    const callback = new URL("/auth/callback", window.location.origin);
    callback.searchParams.set(
      "next",
      next.startsWith("/") ? next : "/documents"
    );

    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: {
        emailRedirectTo: callback.toString()
      }
    });

    setState(error ? "error" : "sent");
  }

  return (
    <main className="auth-page">
      <div className="auth-shell">
        <Brand />

        <section className="auth-card">
          <span className="eyebrow">حساب نَضِيد</span>
          <h1>ادخل إلى مستنداتك</h1>
          <p>
            سنرسل إلى بريدك رابط دخول آمنًا. لا تحتاج إلى إنشاء كلمة مرور
            إضافية لنَضِيد.
          </p>

          {state === "sent" ? (
            <div className="auth-success">
              <strong>تحقق من بريدك</strong>
              <span>
                أرسلنا رابط الدخول إلى {email}. افتحه للمتابعة إلى نَضِيد.
              </span>
            </div>
          ) : (
            <form className="auth-form" onSubmit={submit}>
              <label htmlFor="email">البريد الإلكتروني</label>
              <input
                id="email"
                type="email"
                dir="ltr"
                autoComplete="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@example.com"
              />

              <button
                className="button button-primary auth-submit"
                disabled={state === "sending"}
              >
                {state === "sending"
                  ? "جارٍ إرسال الرابط…"
                  : "إرسال رابط الدخول"}
              </button>
            </form>
          )}

          {state === "error" && (
            <div className="auth-error">
              تعذر إرسال رابط الدخول. تحقق من البريد وحاول مرة أخرى.
            </div>
          )}

          {state === "unavailable" && (
            <div className="auth-error">
              المصادقة غير مفعلة في بيئة التشغيل الحالية بعد.
            </div>
          )}

          <Link href="/" className="auth-back">
            العودة إلى الصفحة الرئيسية
          </Link>
        </section>
      </div>
    </main>
  );
}
