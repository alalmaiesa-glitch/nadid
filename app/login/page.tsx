"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { Brand } from "@/components/SiteHeader";
import { getSupabaseBrowser } from "@/lib/supabase-browser";
import { safeInternalNext } from "@/lib/auth-routing";

type State = "idle" | "sending" | "sent" | "error" | "unavailable";

function safeNext() {
  if (typeof window === "undefined") return "/documents";
  return safeInternalNext(
    new URLSearchParams(window.location.search).get("next"),
    "/documents"
  );
}

export default function LoginPage() {
  const [emailMode, setEmailMode] = useState<"signup" | "signin">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<State>("idle");
  const [message, setMessage] = useState("");

  const callbackUrl = useMemo(() => {
    if (typeof window === "undefined") return "";
    const callback = new URL("/auth/callback", window.location.origin);
    callback.searchParams.set("next", safeNext());
    return callback.toString();
  }, []);

  function fail(text: string) {
    setMessage(text);
    setState("error");
  }

  async function signInWithGoogle() {
    const supabase = getSupabaseBrowser();
    if (!supabase) {
      setState("unavailable");
      return;
    }

    setState("sending");
    setMessage("");

    const callback = new URL("/auth/callback", window.location.origin);
    callback.searchParams.set("next", safeNext());

    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: callback.toString() }
    });

    if (error) {
      fail(
        error.message.toLowerCase().includes("provider")
          ? "تسجيل الدخول عبر Google غير مفعّل في إعدادات المصادقة بعد."
          : "تعذر بدء التسجيل عبر Google. حاول مرة أخرى."
      );
    }
  }

  async function submitEmail(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const supabase = getSupabaseBrowser();
    if (!supabase) {
      setState("unavailable");
      return;
    }

    setState("sending");
    setMessage("");

    if (emailMode === "signup") {
      const { data, error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: { emailRedirectTo: callbackUrl }
      });

      if (error) {
        fail(
          error.message.toLowerCase().includes("already")
            ? "يوجد حساب بهذا البريد بالفعل. اختر «تسجيل الدخول»."
            : "تعذر إنشاء الحساب. تحقق من البريد وكلمة المرور وحاول مرة أخرى."
        );
        return;
      }

      if (data.session) {
        window.location.assign(safeNext());
        return;
      }

      setState("sent");
      setMessage("أنشئنا الحساب. تحقق من بريدك لتأكيد العنوان ثم ادخل إلى نَضِيد.");
      return;
    }

    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password
    });

    if (error) {
      fail("تعذر تسجيل الدخول. تحقق من البريد وكلمة المرور.");
      return;
    }

    window.location.assign(safeNext());
  }

  return (
    <main className="auth-page account-entry-page">
      <div className="account-entry-shell account-entry-shell-single">
        <Brand />

        <section className="account-entry">
          <div className="account-entry-heading">
            <span className="eyebrow">حسابي</span>
            <p>أنشئ حسابك أو سجّل الدخول باستخدام Google أو البريد الإلكتروني.</p>
          </div>

          <button
            type="button"
            className="social-auth-button"
            onClick={signInWithGoogle}
            disabled={state === "sending"}
          >
            <span className="google-mark" aria-hidden="true">G</span>
            <strong>المتابعة باستخدام Google</strong>
          </button>

          <div className="auth-divider"><span>أو</span></div>

          <section className="auth-method-card auth-method-card-single">
            <div className="auth-method-title">
              <span className="auth-method-icon" aria-hidden="true">✉</span>
              <div>
                <h2>البريد الإلكتروني</h2>
                <p>أنشئ حسابًا بالبريد وكلمة مرور، أو ادخل إلى حساب موجود.</p>
              </div>
            </div>

            <div className="email-mode-switch" role="tablist" aria-label="وضع البريد الإلكتروني">
              <button
                type="button"
                className={emailMode === "signup" ? "active" : ""}
                onClick={() => {
                  setEmailMode("signup");
                  setState("idle");
                  setMessage("");
                }}
              >
                إنشاء حساب
              </button>
              <button
                type="button"
                className={emailMode === "signin" ? "active" : ""}
                onClick={() => {
                  setEmailMode("signin");
                  setState("idle");
                  setMessage("");
                }}
              >
                تسجيل الدخول
              </button>
            </div>

            <form className="auth-form compact-auth-form" onSubmit={submitEmail}>
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

              <label htmlFor="password">كلمة المرور</label>
              <input
                id="password"
                type="password"
                dir="ltr"
                autoComplete={emailMode === "signup" ? "new-password" : "current-password"}
                minLength={8}
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="8 أحرف على الأقل"
              />

              <button
                className="button button-primary auth-submit"
                disabled={state === "sending"}
              >
                {state === "sending"
                  ? "جارٍ المتابعة…"
                  : emailMode === "signup"
                    ? "إنشاء الحساب"
                    : "تسجيل الدخول"}
              </button>
            </form>
          </section>

          {(state === "sent" || state === "error" || state === "unavailable") && (
            <div
              className={
                state === "sent" ? "auth-success account-message" : "auth-error account-message"
              }
            >
              {state === "unavailable"
                ? "المصادقة غير مفعلة في بيئة التشغيل الحالية بعد."
                : message}
            </div>
          )}

          <p className="account-terms">
            بإنشاء الحساب أو المتابعة، فإنك توافق على شروط الاستخدام وسياسة الخصوصية.
          </p>

          <Link href="/" className="auth-back">
            العودة إلى الصفحة الرئيسية
          </Link>
        </section>
      </div>
    </main>
  );
}
