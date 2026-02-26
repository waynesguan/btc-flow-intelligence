import LineChart from "@/components/charts/LineChart";
import WindowTabs from "@/components/layout/WindowTabs";
import { getMetricSeries, normalizeWindow } from "@/lib/api";

type Props = {
  searchParams?: Record<string, string | string[] | undefined>;
};

export default async function MacroPage({ searchParams }: Props) {
  const rawWindow = searchParams?.window;
  const window = normalizeWindow(Array.isArray(rawWindow) ? rawWindow[0] : rawWindow);

  try {
    const [fed, dxy, y2, y10] = await Promise.all([
      getMetricSeries("fed_balance_sheet_change", window),
      getMetricSeries("dxy", window),
      getMetricSeries("ust_2y_yield", window),
      getMetricSeries("ust_10y_yield", window)
    ]);

    return (
      <section>
        <header className="pageHeader">
          <div>
            <h1>宏观</h1>
            <p>Fed 资产负债表、美元指数与美债收益率的历史轨迹。</p>
          </div>
        </header>

        <WindowTabs pathname="/macro" active={window} />

        <div className="chartStack">
          <LineChart
            title="Fed Balance Sheet Change (30D %)"
            subtitle={`Source: ${fed.meta.source} · Delay: ${fed.meta.delay}`}
            points={fed.data.series.map((point) => ({ ts: point.ts, value: Number(point.value) }))}
            unit="%"
            color="#0ea5e9"
            thresholdLines={[{ name: "Neutral", value: 0 }]}
          />

          <LineChart
            title="Dollar Index Proxy (DXY)"
            subtitle={`Source: ${dxy.meta.source} · Delay: ${dxy.meta.delay}`}
            points={dxy.data.series.map((point) => ({ ts: point.ts, value: Number(point.value) }))}
            unit="index"
            color="#22c55e"
          />

          <LineChart
            title="UST 2Y vs 10Y"
            subtitle={`Source: ${y2.meta.source} · Delay: ${y2.meta.delay}`}
            points={y10.data.series.map((point, idx) => {
              const y2Value = Number(y2.data.series[idx]?.value ?? 0);
              return {
                ts: point.ts,
                value: Number(point.value) - y2Value
              };
            })}
            unit="spread"
            color="#f59e0b"
            thresholdLines={[{ name: "0", value: 0 }]}
          />
        </div>
      </section>
    );
  } catch {
    return (
      <section>
        <header className="pageHeader">
          <div>
            <h1>宏观</h1>
            <p>Fed 资产负债表、美元指数与美债收益率的历史轨迹。</p>
          </div>
        </header>

        <WindowTabs pathname="/macro" active={window} />
        <div className="contentCard">
          <h3>数据初始化中</h3>
          <p>后端仍在拉取或计算宏观历史数据，请稍后刷新。</p>
        </div>
      </section>
    );
  }
}
