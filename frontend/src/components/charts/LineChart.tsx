"use client";

import dynamic from "next/dynamic";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

type Point = { ts: string; value: number };

type Props = {
  title: string;
  subtitle?: string;
  points: Point[];
  unit?: string;
  color?: string;
  thresholdLines?: Array<{ name: string; value: number }>;
};

export default function LineChart({ title, subtitle, points, unit, color = "#f97316", thresholdLines = [] }: Props) {
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
      valueFormatter: (v: number) => `${v.toFixed(2)}${unit ? ` ${unit}` : ""}`
    },
    xAxis: {
      type: "category",
      data: points.map((point) => new Date(point.ts).toISOString().slice(0, 10)),
      axisLine: { lineStyle: { color: "#94a3b8" } },
      axisLabel: { color: "#475569" }
    },
    yAxis: {
      type: "value",
      splitLine: { lineStyle: { color: "#e2e8f0" } },
      axisLabel: { color: "#475569" }
    },
    grid: { left: 40, right: 16, top: 64, bottom: 32 },
    series: [
      {
        type: "line",
        smooth: true,
        data: points.map((point) => point.value),
        showSymbol: false,
        lineStyle: { color, width: 3 },
        areaStyle: {
          color: {
            type: "linear",
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: `${color}66` },
              { offset: 1, color: `${color}05` }
            ]
          }
        },
        markLine: {
          symbol: "none",
          data: thresholdLines.map((line) => ({ yAxis: line.value, name: line.name })),
          lineStyle: { color: "#334155", type: "dashed", width: 1 },
          label: { formatter: "{b}: {c}", color: "#334155" }
        }
      }
    ]
  };

  return (
    <div className="chartCard">
      <ReactECharts option={option} style={{ height: 340 }} notMerge lazyUpdate />
    </div>
  );
}
