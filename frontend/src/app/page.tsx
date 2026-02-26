import LineChart from "@/components/charts/LineChart";
import WindowTabs from "@/components/layout/WindowTabs";
import {
  getCapitalInflowLatest,
  getCapitalInflowSeries,
  getLatestStage,
  getStructureRiskLatest,
  normalizeWindow
} from "@/lib/api";

type Props = {
  searchParams?: Record<string, string | string[] | undefined>;
};

export default async function HomePage({ searchParams }: Props) {
  const rawWindow = searchParams?.window;
  const window = normalizeWindow(Array.isArray(rawWindow) ? rawWindow[0] : rawWindow);

  try {
    const [latestCapital, capitalSeries, latestRisk, latestStage] = await Promise.all([
      getCapitalInflowLatest(),
      getCapitalInflowSeries(window),
      getStructureRiskLatest(),
      getLatestStage()
    ]);

    const points = capitalSeries.data.series.map((point) => ({
      ts: point.ts,
      value: Number(point.value)
    }));

    return (
      <section>
        <header className="pageHeader">
          <div>
            <h1>概览</h1>
            <p>资金回流评分、结构风险评分与阶段判定的实时总览。</p>
          </div>
          <p>数据更新时间: {new Date(latestCapital.updated_at).toLocaleString("zh-CN", { timeZone: "UTC" })} UTC (北京 {new Date(latestCapital.updated_at).toLocaleString("zh-CN", { timeZone: "Asia/Shanghai" })})</p>
        </header>

        <WindowTabs pathname="/" active={window} />

        <div className="metricGrid">
          <article className="metricCard">
            <h3>Capital Inflow Score</h3>
            <strong>{Number(latestCapital.data.value).toFixed(2)}</strong>
            <small>
              {new Date(latestCapital.data.ts).toISOString().slice(0, 10)} · {latestCapital.data.grade ?? "未分级"}
            </small>
          </article>

          <article className="metricCard">
            <h3>Structure Risk Score</h3>
            <strong>{Number(latestRisk.data.value).toFixed(2)}</strong>
            <small>
              {new Date(latestRisk.data.ts).toISOString().slice(0, 10)} · {latestRisk.data.band ?? "未分级"}
            </small>
          </article>

          <article className="metricCard">
            <h3>当前阶段</h3>
            <strong>{latestStage.data.stage_name}</strong>
            <small>置信度: {(latestStage.data.confidence * 100).toFixed(1)}%</small>
          </article>
        </div>

        <div className="chartStack">
          <LineChart
            title="Capital Inflow Score"
            subtitle={`Source: ${capitalSeries.meta.source} · Delay: ${capitalSeries.meta.delay}`}
            points={points}
            unit="score"
            color="#f97316"
            thresholdLines={[
              { name: "Strong", value: 70 },
              { name: "Weak", value: 40 }
            ]}
          />
        </div>
      </section>
    );
  } catch {
    return (
      <section>
        <header className="pageHeader">
          <div>
            <h1>概览</h1>
            <p>资金回流评分、结构风险评分与阶段判定的实时总览。</p>
          </div>
        </header>
        <WindowTabs pathname="/" active={window} />
        <div className="contentCard">
          <h3>数据初始化中</h3>
          <p>后端可能正在执行首次 backfill，请稍后刷新页面。</p>
        </div>
      </section>
    );
  }
}
