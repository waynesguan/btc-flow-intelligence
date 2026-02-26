"use client";

import { useEffect, useMemo, useState } from "react";

import LineChart from "@/components/charts/LineChart";
import MultiSeriesChart from "@/components/charts/MultiSeriesChart";
import { MetricCatalogRow, TimeWindow, getMetricSeries } from "@/lib/api";

type StageStats = {
  stage_days: Array<{ stage_id: number; stage_name: string; days: number }>;
  stage_switches: number;
  score_distribution: Record<string, Record<string, number>>;
  multi_cycle_overlay: Array<{
    label: string;
    start_ts: string;
    end_ts: string;
    points: Array<{ step: number; capital: number; risk: number | null; stage_id: number | null }>;
  }>;
};

type MetricSeriesPayload = {
  metric: { metric_id: string; name: string; unit: string | null; available_since: string | null };
  series: Array<{ ts: string; value: number; aux?: Record<string, unknown> }>;
};

type Props = {
  catalog: MetricCatalogRow[];
  stageStats: StageStats | null;
  window: TimeWindow;
};

export default function MetricExplorer({ catalog, stageStats, window }: Props) {
  const [query, setQuery] = useState("");
  const [selectedMetric, setSelectedMetric] = useState<string>(catalog[0]?.metric_id ?? "");
  const [metricData, setMetricData] = useState<MetricSeriesPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const filteredCatalog = useMemo(() => {
    if (!query.trim()) {
      return catalog;
    }
    const q = query.trim().toLowerCase();
    return catalog.filter((item) => item.metric_id.toLowerCase().includes(q) || item.name.toLowerCase().includes(q));
  }, [catalog, query]);

  const selectedMeta = useMemo(
    () => catalog.find((item) => item.metric_id === selectedMetric) ?? null,
    [catalog, selectedMetric]
  );

  useEffect(() => {
    if (!selectedMetric) {
      setMetricData(null);
      return;
    }

    let mounted = true;
    setLoading(true);
    setError(null);

    getMetricSeries(selectedMetric, window)
      .then((res) => {
        if (!mounted) {
          return;
        }
        setMetricData(res.data);
      })
      .catch((err) => {
        if (!mounted) {
          return;
        }
        setMetricData(null);
        setError(err instanceof Error ? err.message : "metric fetch failed");
      })
      .finally(() => {
        if (mounted) {
          setLoading(false);
        }
      });

    return () => {
      mounted = false;
    };
  }, [selectedMetric, window]);

  const overlayLabels = useMemo(() => {
    const maxLen = stageStats?.multi_cycle_overlay.reduce((acc, cycle) => Math.max(acc, cycle.points.length), 0) ?? 0;
    return Array.from({ length: maxLen }, (_, idx) => String(idx + 1));
  }, [stageStats]);

  const overlaySeries = useMemo(() => {
    if (!stageStats) {
      return [];
    }
    const palette = ["#f97316", "#0ea5e9", "#22c55e"];
    return stageStats.multi_cycle_overlay.map((cycle, idx) => ({
      name: cycle.label,
      color: palette[idx % palette.length],
      data: overlayLabels.map((_, pos) => Number(cycle.points[pos]?.capital ?? NaN))
    }));
  }, [overlayLabels, stageStats]);

  return (
    <div className="metricExplorer">
      <section className="contentCard">
        <h3>指标筛选</h3>
        <input
          className="metricSearch"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="输入 metric_id 或指标名称"
        />

        <table className="table" style={{ marginTop: 10 }}>
          <thead>
            <tr>
              <th>Metric ID</th>
              <th>维度</th>
              <th>Tier</th>
              <th>领先性</th>
              <th>来源</th>
            </tr>
          </thead>
          <tbody>
            {filteredCatalog.map((row) => {
              const active = row.metric_id === selectedMetric;
              return (
                <tr
                  key={row.metric_id}
                  onClick={() => setSelectedMetric(row.metric_id)}
                  className={active ? "metricRow active" : "metricRow"}
                >
                  <td>{row.metric_id}</td>
                  <td>{row.dimension}</td>
                  <td>{row.tier}</td>
                  <td>{row.lead_lag}</td>
                  <td>{Array.isArray(row.source_priority?.sources) ? row.source_priority.sources.join(", ") : "n/a"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>

      <section className="contentCard" style={{ marginTop: 12 }}>
        <h3>单指标详情</h3>
        {!selectedMeta ? <p>暂无可用指标。</p> : null}
        {selectedMeta ? (
          <>
            <p><strong>{selectedMeta.name}</strong> ({selectedMeta.metric_id})</p>
            <p>{selectedMeta.definition_short}</p>
            <p style={{ color: "#334155" }}>{selectedMeta.definition_pro}</p>
            <p>公式: {selectedMeta.calc_spec?.formula ?? "n/a"}</p>
            <p>输入: {Array.isArray(selectedMeta.calc_spec?.inputs) ? selectedMeta.calc_spec.inputs.join(", ") : "n/a"}</p>
            <p>available_since: {selectedMeta.available_since ?? "n/a"}</p>
          </>
        ) : null}

        {loading ? <p>加载指标时序中...</p> : null}
        {error ? <p>指标时序加载失败: {error}</p> : null}

        {metricData && metricData.series.length > 0 ? (
          <LineChart
            title={`${metricData.metric.name} (${metricData.metric.metric_id})`}
            subtitle={`Window: ${window} · Unit: ${metricData.metric.unit ?? "n/a"}`}
            points={metricData.series.map((point) => ({ ts: point.ts, value: Number(point.value) }))}
            unit={metricData.metric.unit ?? undefined}
            color="#0ea5e9"
          />
        ) : null}
      </section>

      {stageStats ? (
        <section className="contentCard" style={{ marginTop: 12 }}>
          <h3>阶段统计面板</h3>
          <div className="metricGrid" style={{ marginTop: 10 }}>
            <article className="metricCard">
              <h3>阶段切换次数</h3>
              <strong>{stageStats.stage_switches}</strong>
              <small>统计窗口: {window}</small>
            </article>
            <article className="metricCard">
              <h3>Capital Score 平均值</h3>
              <strong>{Number(stageStats.score_distribution.capital_inflow_score?.mean ?? 0).toFixed(2)}</strong>
              <small>中位数: {Number(stageStats.score_distribution.capital_inflow_score?.median ?? 0).toFixed(2)}</small>
            </article>
            <article className="metricCard">
              <h3>Risk Score 平均值</h3>
              <strong>{Number(stageStats.score_distribution.structure_risk_score?.mean ?? 0).toFixed(2)}</strong>
              <small>中位数: {Number(stageStats.score_distribution.structure_risk_score?.median ?? 0).toFixed(2)}</small>
            </article>
          </div>

          <table className="table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>阶段</th>
                <th>累计天数</th>
              </tr>
            </thead>
            <tbody>
              {stageStats.stage_days.map((row) => (
                <tr key={row.stage_id}>
                  <td>{row.stage_name}</td>
                  <td>{row.days}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {overlaySeries.length > 0 ? (
            <MultiSeriesChart
              title="Capital Inflow 多周期叠加"
              subtitle="按最近三个 90 日窗口叠加比较"
              labels={overlayLabels}
              series={overlaySeries}
              unit="score"
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
