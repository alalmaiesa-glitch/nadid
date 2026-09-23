import { getSupabaseAdmin } from "@/lib/supabase-admin";

function configured(name: string) {
  return Boolean(process.env[name]);
}

export async function GET() {
  const configuration = {
    supabaseUrl: configured("NEXT_PUBLIC_SUPABASE_URL"),
    supabasePublishableKey: configured("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY"),
    supabaseServiceRole: configured("SUPABASE_SERVICE_ROLE_KEY"),
    aeeUrl: configured("AEE_BACKEND_URL"),
    aeeInternalToken: configured("AEE_INTERNAL_TOKEN")
  };

  const configurationReady = Object.values(configuration).every(Boolean);

  let database = false;
  let aee = false;

  const supabase = getSupabaseAdmin();

  if (supabase) {
    const { error } = await supabase
      .from("documents")
      .select("id", { head: true, count: "exact" })
      .limit(1);

    database = !error;
  }

  const aeeBase = process.env.AEE_BACKEND_URL?.replace(/\/$/, "");

  if (aeeBase) {
    try {
      const response = await fetch(aeeBase + "/health", {
        cache: "no-store",
        signal: AbortSignal.timeout(5_000)
      });

      aee = response.ok;
    } catch {
      aee = false;
    }
  }

  const ready = configurationReady && database && aee;

  return Response.json(
    {
      status: ready ? "ready" : "not_ready",
      components: {
        configuration: configurationReady,
        database,
        aee
      },
      configuration
    },
    {
      status: ready ? 200 : 503,
      headers: {
        "Cache-Control": "no-store"
      }
    }
  );
}
