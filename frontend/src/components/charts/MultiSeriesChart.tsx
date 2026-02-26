"use client";

import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type SeriesDef = {
  name: string;
  data: number[];
  color?: string;
  type?: "line" | "bar";
  stack?: string;
};

type Props = {
  title: string;
  subtitle?: string;
  labels: string[];
  series: SeriesDef[];
  unit?: string;
};

export default function MultiSeriesChart({ title, subtitle, labels, series, unit }: Props) {
  const option = {
    backgroundColor: "transparent",
    title: {
      text: title,
      subtext: subtitle,
      textStyle: { color: "#0f172a", fontWeight: 600, fontSize: 16 },
      subtextStyle: { color: "#475569", fontSize: 12 }
    },
    tooltip: {
      trigger: "axis",
      valueFormatter: (v: number) => `${Number(v).toFixed(2)}${unit ? ` ${unit}` : ""}`
    },
    legend: {
      top: 30,
      textStyle: { color: "#334155", fontSize: 11 }
    },
    xAxis: {
      type: "category",
      data: labels,
      axisLine: { lineStyle: { color: "#94a3b8" } },
      axisLabel: { color: "#475569" }
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: { color: "#475569" }
    },
    grid: { left: 40, right: 16, top: 88, bottom: 36 },
    series: series.map((entry) => ({
      name: entry.name,
      type: entry.type ?? "line",
      stack: entry.stack,
      data: entry.data,
      showSymbol: false,
      smooth: entry.type !== "bar",
      itemStyle: { color: entry.color },
      lineStyle: { color: entry.color, width: 2 },
      emphasis: { focus: "series" }
    }))
  };

  return (
    <div className="chartCard">
      <ReactECharts option={option} style={{ height: 360 }} notMerge lazyUpdate />
    </div>
  );
}
