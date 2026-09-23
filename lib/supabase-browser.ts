"use client";

import { createBrowserClient } from "@supabase/ssr";
import type { SupabaseClient } from "@supabase/supabase-js";
import type { Database } from "@/lib/database.types";

let cached: SupabaseClient<Database> | null | undefined;

export function getSupabaseBrowser() {
  if (cached !== undefined) return cached;

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;

  if (!url || !key) {
    cached = null;
    return cached;
  }

  cached = createBrowserClient<Database>(url, key);
  return cached;
}
