"use client";

import { FormEvent, useMemo, useState } from "react";
import Link from "next/link";
import { Brand } from "@/components/SiteHeader";
import { getSupabaseBrowser } from "@/lib/supabase-browser";

type State =
  | "idle"
  | "sending"
  | "sent"
  | "error"
  | "unavailable";

function safeNext() {
  if (typeof window === "undefined") return "/documents";
  const requested =
    new URLSearchParams(window.location.search).get("next") ?? "/documents";
  return requested.startsWith("/") &&
    !requested.startsWith("//") &&
    !requested.startsWith("/\\")
    ? requested
    : "/documents";
}

function normalizeSaudiPhone(raw: string) {
  const cleaned = raw.replace(/[\s()-]/g, "");
  if (cleaned.startsWith("+")) return cleaned;
  if (cleaned.startsWith("00966")) return "+" + cleaned.slice(2);
  if (cleaned.startsWith("966")) return "+" + cleaned;
  if (cleaned.startsWith("05")) return "+966" + cleaned.slice(1);
  if (cleaned.startsWith("5")) return "+966" + cleaned;
  return cleaned;
}

export default function LoginPage() {
  const [emailMode, setEmailMode] = useState<"signup" | "signin">("signup");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [phoneToken, setPhoneToken] = useState("");
  const [phoneSent, setPhoneSent] = useState(false);
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
      options: {
        redirectTo: callback.toString()
      }
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
        options: {
          emailRedirectTo: callbackUrl
        }
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

  async function sendPhoneCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const supabase = getSupabaseBrowser();
    if (!supabase) {
      setState("unavailable");
      return;
    }

    const normalized = normalizeSaudiPhone(phone);
    if (!/^\+[1-9]\d{7,14}$/.test(normalized)) {
      fail("أدخل رقم الجوال بصيغة صحيحة، مثل 05xxxxxxxx.");
      return;
    }

    setState("sending");
    setMessage("");

    const { error } = await supabase.auth.signInWithOtp({
      phone: normalized,
      options: {
        shouldCreateUser: true
      }
    });

    if (error) {
      fail(
        error.message.toLowerCase().includes("provider")
          ? "التسجيل برقم الجوال يحتاج تفعيل مزود رسائل SMS في إعدادات نَضِيد."
          : "تعذر إرسال رمز التحقق إلى رقم الجوال."
      );
      return;
    }

    setPhone(normalized);
    setPhoneSent(true);
    setState("sent");
    setMessage("أرسلنا رمز تحقق إلى رقم الجوال.");
  }

  async function verifyPhoneCode(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const supabase = getSupabaseBrowser();
    if (!supabase) {
      setState("unavailable");
      return;
    }

    setState("sending");
    setMessage("");

    const { error } = await supabase.auth.verifyOtp({
      phone: normalizeSaudiPhone(phone),
      token: phoneToken.trim(),
      type: "sms"
    });

    if (error) {
      fail("رمز التحقق غير صحيح أو انتهت صلاحيته.");
      return;
    }

    window.location.assign(safeNext());
  }

  return (
    <main className="auth-page account-entry-page">
      <div className="account-entry-shell">
        <Brand />

        <section className="account-entry">
          <div className="account-entry-heading">
            <span className="eyebrow">حسابي</span>
            <p>اختر الطريقة الأنسب لإنشاء حسابك أو الدخول إلى نَضِيد.</p>
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

          <div className="auth-method-grid">
            <section className="auth-method-card">
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

            <section className="auth-method-card">
              <div className="auth-method-title">
                <span className="auth-method-icon" aria-hidden="true">⌕</span>
                <div>
                  <h2>رقم الجوال</h2>
                  <p>استقبل رمز تحقق لمرة واحدة على جوالك.</p>
                </div>
              </div>

              {!phoneSent ? (
                <form className="auth-form compact-auth-form" onSubmit={sendPhoneCode}>
                  <label htmlFor="phone">رقم الجوال</label>
                  <input
                    id="phone"
                    type="tel"
                    dir="ltr"
                    autoComplete="tel"
                    required
                    value={phone}
                    onChange={(event) => setPhone(event.target.value)}
                    placeholder="05xxxxxxxx"
                  />
                  <button
                    className="button button-secondary auth-submit"
                    disabled={state === "sending"}
                  >
                    إرسال رمز التحقق
                  </button>
                </form>
              ) : (
                <form className="auth-form compact-auth-form" onSubmit={verifyPhoneCode}>
                  <label htmlFor="phone-token">رمز التحقق</label>
                  <input
                    id="phone-token"
                    type="text"
                    inputMode="numeric"
                    dir="ltr"
                    autoComplete="one-time-code"
                    minLength={6}
                    maxLength={6}
                    required
                    value={phoneToken}
                    onChange={(event) =>
                      setPhoneToken(event.target.value.replace(/\D/g, "").slice(0, 6))
                    }
                    placeholder="000000"
                  />
                  <button
                    className="button button-primary auth-submit"
                    disabled={state === "sending"}
                  >
                    تأكيد الرقم والمتابعة
                  </button>
                  <button
                    type="button"
                    className="text-button phone-change"
                    onClick={() => {
                      setPhoneSent(false);
                      setPhoneToken("");
                      setState("idle");
                      setMessage("");
                    }}
                  >
                    تغيير رقم الجوال
                  </button>
                </form>
              )}
            </section>
          </div>

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
