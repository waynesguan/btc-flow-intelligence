import { getMetricCatalog } from "@/lib/api";

export default async function MetricsPage() {
  const catalog = await getMetricCatalog("must_have");

  return (
    <section>
      <header className="pageHeader">
        <div>
          <h1>指标详情</h1>
          <p>Phase 1 提供 must_have 指标口径、来源与公式信息。</p>
        </div>
      </header>

      <div className="contentCard">
        <table className="table">
          <thead>
            <tr>
              <th>Metric ID</th>
              <th>维度</th>
              <th>领先性</th>
              <th>来源</th>
              <th>公式</th>
            </tr>
          </thead>
          <tbody>
            {catalog.data.map((row) => (
              <tr key={String(row.metric_id)}>
                <td>{String(row.metric_id)}</td>
                <td>{String(row.dimension)}</td>
                <td>{String(row.lead_lag)}</td>
                <td>{Array.isArray((row.source_priority as { sources?: string[] }).sources) ? (row.source_priority as { sources: string[] }).sources.join(", ") : "n/a"}</td>
                <td>{String((row.calc_spec as { formula?: string }).formula ?? "n/a")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
