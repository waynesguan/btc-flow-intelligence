import MultiSeriesChart from "@/components/charts/MultiSeriesChart";
import WindowTabs from "@/components/layout/WindowTabs";
import {
  getMetricSeries,
  getStructureRiskLatest,
  getStructureRiskSeries,
  normalizeWindow
} from "@/lib/api";

type Props = {
  searchParams?: Record<string, string | string[] | undefined>;
};

export default async function StructureRiskPage({ searchParams }: Props) {
  const rawWindow = searchParams?.window;
  const window = normalizeWindow(Array.isArray(rawWindow) ? rawWindow[0] : rawWindow);

  try {
    const [riskLatest, riskSeries, leverage, basis, liquidation] = await Promise.all([
      getStructureRiskLatest(),
      getStructureRiskSeries(window),
      getMetricSeries("leverage_risk_index", window),
      getMetricSeries("basis_spread", window),
      getMetricSeries("liquidation_volume", window)
    ]);

    const riskLabels = riskSeries.data.series.map((point) => new Date(point.ts).toISOString().slice(0, 10));
    const riskChartSeries = [
      {
        name: "Structure Risk Score",
        color: "#dc2626",
        data: riskSeries.data.series.map((point) => Number(point.value))
      }
    ];

    const metricLabels = leverage.data.series.map((point) => new Date(point.ts).toISOString().slice(0, 10));
    const metricSeries = [
      {
        name: "Leverage Risk Index",
        color: "#f97316",
        data: leverage.data.series.map((point) => Number(point.value))
      },
      {
        name: "Basis Spread",
        color: "#0ea5e9",
        data: basis.data.series.map((point) => Number(point.value))
      },
      {
        name: "Liquidation Volume",
        color: "#8b5cf6",
        data: liquidation.data.series.map((point) => Number(point.value))
      }
    ];

    const components = (riskLatest.data.components?.components ?? {}) as Record<string, number>;

    return (
      <section>
        <header className="pageHeader">
          <div>
            <h1>结构风险</h1>
            <p>杠杆风险、基差、清算代理与结构风险评分分解。</p>
          </div>
          <p>更新时间: {new Date(riskLatest.updated_at).toLocaleString("zh-CN")}</p>
        </header>

        <WindowTabs pathname="/structure-risk" active={window} />

        <div className="metricGrid">
          <article className="metricCard">
            <h3>Structure Risk Score</h3>
            <strong>{Number(riskLatest.data.value).toFixed(2)}</strong>
            <small>{String(riskLatest.data.band ?? "未分级")}</small>
          </article>
          <article className="metricCard">
            <h3>可用组件数</h3>
            <strong>{Number((riskLatest.data.components?.available_components as number) ?? 0)}</strong>
            <small>自动权重重归一化: {String((riskLatest.data.components?.renormalized as boolean) ?? false)}</small>
          </article>
          <article className="metricCard">
            <h3>风险带</h3>
            <strong>{String((riskLatest.data.components?.band as string) ?? "未知")}</strong>
            <small>阈值: high=70 / moderate=40</small>
          </article>
        </div>

        <div className="chartStack">
          <MultiSeriesChart
            title="Structure Risk Score"
            subtitle={`Source: ${riskSeries.meta.source} · Delay: ${riskSeries.meta.delay}`}
            labels={riskLabels}
            series={riskChartSeries}
            unit="score"
          />

          <MultiSeriesChart
            title="Leverage / Basis / Liquidation"
            subtitle={`Source: ${leverage.meta.source} + ${basis.meta.source} + ${liquidation.meta.source}`}
            labels={metricLabels}
            series={metricSeries}
            unit="index"
          />
        </div>

        <section className="contentCard" style={{ marginTop: 12 }}>
          <h3>结构风险评分分解</h3>
          <table className="table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>组件</th>
                <th>标准化得分</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(components).map(([key, value]) => (
                <tr key={key}>
                  <td>{key}</td>
                  <td>{Number(value).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </section>
    );
  } catch {
    return (
      <section className="contentCard">
        <h1>结构风险</h1>
        <p>数据初始化中或数据源暂时不可用，请稍后刷新。</p>
      </section>
    );
  }
}
