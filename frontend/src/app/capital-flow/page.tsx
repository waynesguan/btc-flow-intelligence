import MultiSeriesChart from "@/components/charts/MultiSeriesChart";
import WindowTabs from "@/components/layout/WindowTabs";
import {
  getCapitalInflowLatest,
  getMetricSeries,
  normalizeWindow
} from "@/lib/api";

type Props = {
  searchParams?: Record<string, string | string[] | undefined>;
};

function extractByFund(value: unknown): Record<string, number> {
  if (!value || typeof value !== "object") {
    return {};
  }
  const casted = value as { by_fund?: Record<string, unknown> };
  if (!casted.by_fund || typeof casted.by_fund !== "object") {
    return {};
  }
  return Object.entries(casted.by_fund).reduce<Record<string, number>>((acc, [key, val]) => {
    const num = Number(val);
    if (!Number.isNaN(num)) {
      acc[key] = num;
    }
    return acc;
  }, {});
}

export default async function CapitalFlowPage({ searchParams }: Props) {
  const rawWindow = searchParams?.window;
  const window = normalizeWindow(Array.isArray(rawWindow) ? rawWindow[0] : rawWindow);

  try {
    const [etfByFund, usdt, usdc, stableNet, capitalLatest] = await Promise.all([
      getMetricSeries("us_spot_etf_netflow_by_fund", window),
      getMetricSeries("usdt_supply_change", window),
      getMetricSeries("usdc_supply_change", window),
      getMetricSeries("stablecoin_net_mint_burn", window),
      getCapitalInflowLatest()
    ]);

    const labels = etfByFund.data.series.map((point) => new Date(point.ts).toISOString().slice(0, 10));

    const fundTotals: Record<string, number> = {};
    etfByFund.data.series.forEach((point) => {
      const byFund = extractByFund(point.aux);
      Object.entries(byFund).forEach(([fund, value]) => {
        fundTotals[fund] = (fundTotals[fund] ?? 0) + Math.abs(value);
      });
    });

    const topFunds = Object.entries(fundTotals)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([fund]) => fund);

    const fundSeries = topFunds.map((fund, idx) => ({
      name: fund,
      type: "bar" as const,
      stack: "etf",
      color: ["#2563eb", "#f97316", "#10b981", "#ec4899", "#14b8a6", "#64748b"][idx % 6],
      data: etfByFund.data.series.map((point) => {
        const byFund = extractByFund(point.aux);
        return byFund[fund] ?? 0;
      })
    }));

    const stableLabels = stableNet.data.series.map((point) => new Date(point.ts).toISOString().slice(0, 10));
    const stableSeries = [
      {
        name: "USDT Supply Change",
        color: "#16a34a",
        data: usdt.data.series.map((point) => Number(point.value))
      },
      {
        name: "USDC Supply Change",
        color: "#0ea5e9",
        data: usdc.data.series.map((point) => Number(point.value))
      },
      {
        name: "Net Mint/Burn",
        color: "#f59e0b",
        data: stableNet.data.series.map((point) => Number(point.value))
      }
    ];

    const scoreComponents = (capitalLatest.data.components?.components ?? {}) as Record<string, number>;

    return (
      <section>
        <header className="pageHeader">
          <div>
            <h1>资金流</h1>
            <p>ETF 分基金流入、稳定币流动性与资金回流评分分解。</p>
          </div>
          <p>更新时间: {new Date(capitalLatest.updated_at).toLocaleString("zh-CN")}</p>
        </header>

        <WindowTabs pathname="/capital-flow" active={window} />

        <div className="metricGrid">
          <article className="metricCard">
            <h3>Capital Inflow Score</h3>
            <strong>{Number(capitalLatest.data.value).toFixed(2)}</strong>
            <small>{String(capitalLatest.data.grade ?? "未分级")}</small>
          </article>
          <article className="metricCard">
            <h3>可用组件数</h3>
            <strong>{Number((capitalLatest.data.components?.available_components as number) ?? 0)}</strong>
            <small>自动权重重归一化: {String((capitalLatest.data.components?.renormalized as boolean) ?? false)}</small>
          </article>
          <article className="metricCard">
            <h3>强回流连续条件</h3>
            <strong>{String((capitalLatest.data.components?.is_strong_sustained as boolean) ? "满足" : "未满足")}</strong>
            <small>规则: >=70 且连续 7 天不低于 60</small>
          </article>
        </div>

        <div className="chartStack">
          <MultiSeriesChart
            title="US Spot ETF Netflow By Fund"
            subtitle={`Source: ${etfByFund.meta.source} · Delay: ${etfByFund.meta.delay}`}
            labels={labels}
            series={fundSeries}
            unit="USD_million"
          />

          <MultiSeriesChart
            title="Stablecoin Liquidity"
            subtitle={`Source: ${stableNet.meta.source} · Delay: ${stableNet.meta.delay}`}
            labels={stableLabels}
            series={stableSeries}
            unit="%"
          />
        </div>

        <section className="contentCard" style={{ marginTop: 12 }}>
          <h3>资金回流评分分解</h3>
          <table className="table" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>组件</th>
                <th>标准化得分</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(scoreComponents).map(([key, value]) => (
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
        <h1>资金流</h1>
        <p>数据初始化中或数据源暂时不可用，请稍后刷新。</p>
      </section>
    );
  }
}
