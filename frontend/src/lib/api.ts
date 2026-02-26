export type ApiEnvelope<T> = {
  data: T;
  meta: {
    source: string | null;
    delay: string | null;
    unit: string | null;
    version: number;
  };
  updated_at: string;
};

export type SeriesPoint = {
  ts: string;
  value: number;
  aux?: Record<string, unknown>;
  components?: Record<string, unknown>;
};

export type MetricCatalogRow = {
  metric_id: string;
  name: string;
  dimension: number;
  lead_lag: string;
  definition_short: string;
  definition_pro: string;
  calc_spec: { formula?: string; inputs?: string[] };
  source_priority: { sources?: string[] };
  refresh_policy: Record<string, unknown>;
  failure_modes: Record<string, unknown>;
  chart_spec: { unit?: string };
  tier: string;
  version: number;
  available_since: string | null;
};

export type TimeWindow = "7D" | "30D" | "90D" | "1Y" | "ALL";

export const WINDOW_OPTIONS: TimeWindow[] = ["7D", "30D", "90D", "1Y", "ALL"];

const publicBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
const internalBase = process.env.INTERNAL_API_BASE ?? publicBase;

async function fetchJson<T>(path: string): Promise<T> {
  const response = await fetch(`${internalBase}${path}`, {
    cache: "no-store",
    headers: {
      "Content-Type": "application/json"
    }
  });

  if (!response.ok) {
    throw new Error(`API request failed: ${path} (${response.status})`);
  }

  return response.json() as Promise<T>;
}

function windowStartIso(window: TimeWindow): string | null {
  if (window === "ALL") {
    return null;
  }

  const now = new Date();
  if (window === "1Y") {
    now.setUTCFullYear(now.getUTCFullYear() - 1);
  } else {
    const days = Number(window.replace("D", ""));
    now.setUTCDate(now.getUTCDate() - days);
  }
  return now.toISOString();
}

function withQuery(path: string, query: Record<string, string | null | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(query).forEach(([key, value]) => {
    if (value !== null && value !== undefined && value !== "") {
      params.set(key, value);
    }
  });
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export function normalizeWindow(value?: string): TimeWindow {
  const upper = (value ?? "ALL").toUpperCase();
  if (WINDOW_OPTIONS.includes(upper as TimeWindow)) {
    return upper as TimeWindow;
  }
  return "ALL";
}

export async function getCapitalInflowLatest() {
  return fetchJson<
    ApiEnvelope<{
      score_id: string;
      ts: string;
      value: number;
      grade?: string;
      components: Record<string, unknown>;
    }>
  >("/scores/capital_inflow/latest");
}

export async function getStructureRiskLatest() {
  return fetchJson<
    ApiEnvelope<{
      score_id: string;
      ts: string;
      value: number;
      band?: string;
      components: Record<string, unknown>;
    }>
  >("/scores/structure_risk/latest");
}

export async function getCapitalInflowSeries(window: TimeWindow = "ALL") {
  return fetchJson<ApiEnvelope<{ score_id: string; series: SeriesPoint[] }>>(
    withQuery("/scores/capital_inflow", {
      granularity: "daily",
      start: windowStartIso(window)
    })
  );
}

export async function getStructureRiskSeries(window: TimeWindow = "ALL") {
  return fetchJson<ApiEnvelope<{ score_id: string; series: SeriesPoint[] }>>(
    withQuery("/scores/structure_risk", {
      granularity: "daily",
      start: windowStartIso(window)
    })
  );
}

export async function getScoreSeries(scoreId: string, window: TimeWindow = "ALL") {
  return fetchJson<ApiEnvelope<{ score_id: string; series: SeriesPoint[] }>>(
    withQuery(`/scores/${scoreId}`, {
      granularity: "daily",
      start: windowStartIso(window)
    })
  );
}

export async function getLatestStage() {
  return fetchJson<
    ApiEnvelope<{
      ts: string;
      stage_id: number;
      stage_name: string;
      confidence: number;
      explanation_public: string;
      evidence: Record<string, unknown>;
    }>
  >("/stage/latest");
}

export async function getStageStats(window: TimeWindow = "ALL") {
  return fetchJson<
    ApiEnvelope<{
      stage_days: Array<{ stage_id: number; stage_name: string; days: number }>;
      stage_switches: number;
      score_distribution: Record<string, Record<string, number>>;
      multi_cycle_overlay: Array<{
        label: string;
        start_ts: string;
        end_ts: string;
        points: Array<{ step: number; capital: number; risk: number | null; stage_id: number | null }>;
      }>;
    }>
  >(
    withQuery("/stage/stats", {
      start: windowStartIso(window)
    })
  );
}

export async function getMetricSeries(metricId: string, window: TimeWindow = "ALL") {
  return fetchJson<
    ApiEnvelope<{
      metric: { metric_id: string; name: string; unit: string | null; available_since: string | null };
      series: SeriesPoint[];
    }>
  >(
    withQuery(`/metrics/${metricId}`, {
      granularity: "daily",
      start: windowStartIso(window)
    })
  );
}

export async function getMetricCatalog(tier?: string) {
  const query = tier ? `?tier=${tier}` : "";
  return fetchJson<ApiEnvelope<MetricCatalogRow[]>>(`/metrics/catalog${query}`);
}

export function browserApiBase(): string {
  return publicBase;
}
