import WindowTabs from "@/components/layout/WindowTabs";
import MetricExplorer from "@/components/metrics/MetricExplorer";
import { getMetricCatalog, getStageStats, normalizeWindow } from "@/lib/api";

type Props = {
  searchParams?: Record<string, string | string[] | undefined>;
};

export default async function MetricsPage({ searchParams }: Props) {
  const rawWindow = searchParams?.window;
  const window = normalizeWindow(Array.isArray(rawWindow) ? rawWindow[0] : rawWindow);

  const [mustHave, niceToHave, stageStats] = await Promise.all([
    getMetricCatalog("must_have"),
    getMetricCatalog("nice_to_have"),
    getStageStats(window).catch(() => null)
  ]);

  const catalog = [...mustHave.data, ...niceToHave.data].sort((a, b) => {
    if (a.dimension === b.dimension) {
      return a.metric_id.localeCompare(b.metric_id);
    }
    return a.dimension - b.dimension;
  });

  return (
    <section>
      <header className="pageHeader">
        <div>
          <h1>指标详情</h1>
          <p>点击单个指标展开时序图表，并查看阶段统计与回测叠加。</p>
        </div>
      </header>

      <WindowTabs pathname="/metrics" active={window} />
      <MetricExplorer catalog={catalog} stageStats={stageStats?.data ?? null} window={window} />
    </section>
  );
}
