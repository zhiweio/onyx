"use client";

import React from "react";
import {
  Bar,
  BarChart as ReChartsBarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { cn } from "@opal/utils";

const DEFAULT_COLORS = [
  "var(--theme-purple-05)",
  "var(--theme-magenta-05)",
] as const;

export interface BarChartProps {
  data?: Array<Record<string, string | number>>;
  categories?: string[];
  index?: string;
  colors?: readonly string[];
  className?: string;
  yAxisFormatter?: (value: number) => string;
}

export default function BarChart({
  data = [],
  categories = [],
  index,
  colors = DEFAULT_COLORS,
  className,
  yAxisFormatter = (value: number) => value.toString(),
}: BarChartProps) {
  return (
    <div dir="ltr" className={cn("h-[280px] w-full", className)}>
      <ResponsiveContainer width="100%" height="100%">
        <ReChartsBarChart
          data={data}
          margin={{ top: 10, right: 16, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis
            dataKey={index}
            tickLine={false}
            axisLine={false}
            tickMargin={8}
          />
          <YAxis
            width={56}
            tickLine={false}
            axisLine={false}
            tickFormatter={(value) => yAxisFormatter(Number(value))}
          />
          <Tooltip />
          {categories.map((category, ind) => (
            <Bar
              key={category}
              dataKey={category}
              fill={colors[ind % colors.length]}
              radius={[4, 4, 0, 0]}
            />
          ))}
        </ReChartsBarChart>
      </ResponsiveContainer>
    </div>
  );
}
