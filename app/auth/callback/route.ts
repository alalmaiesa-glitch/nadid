import { NextResponse } from "next/server";
import { getSupabaseServer } from "@/lib/supabase-server";
import { safeInternalNext } from "@/lib/auth-routing";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const next = safeInternalNext(
    url.searchParams.get("next"),
    "/documents"
  );

  if (!code) {
    return NextResponse.redirect(
      new URL("/login?error=missing_code", url.origin)
    );
  }

  const supabase = await getSupabaseServer();

  if (!supabase) {
    return NextResponse.redirect(
      new URL("/login?error=auth_unavailable", url.origin)
    );
  }

  const { error } = await supabase.auth.exchangeCodeForSession(code);

  if (error) {
    return NextResponse.redirect(
      new URL("/login?error=exchange_failed", url.origin)
    );
  }

  return NextResponse.redirect(new URL(next, url.origin));
}
