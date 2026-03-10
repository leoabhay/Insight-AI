"use client";

import { useState, useCallback, useRef } from "react";
import { useDropzone } from "react-dropzone";
import axios from "axios";
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";

// Types
interface DataPoint {
  x: string | number;
  y: number | null;
}
interface DataSeries {
  name: string;
  data: DataPoint[];
}
interface CSVResult {
  upload_id: string;
  filename: string;
  row_count: number;
  col_count: number;
  columns: string[];
  dtypes: Record<string, string>;
  sample_rows: Record<string, unknown>[];
  numeric_summary: Record<string, Record<string, number>>;
  data_series: DataSeries[];
  category_series: DataSeries[];
  processed_at: string;
}

// Palette
const COLORS = [
  "#38bdf8",
  "#a78bfa",
  "#34d399",
  "#fb923c",
  "#f472b6",
  "#facc15",
  "#60a5fa",
  "#4ade80",
];

// Helpers
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function toRechartsData(series: DataSeries[]) {
  // Merge all series into [{x, seriesA, seriesB, ...}]
  const map = new Map<string, Record<string, unknown>>();
  for (const s of series) {
    for (const pt of s.data) {
      const key = String(pt.x);
      if (!map.has(key)) map.set(key, { x: key });
      (map.get(key) as Record<string, unknown>)[s.name] = pt.y;
    }
  }
  return Array.from(map.values());
}

// Component
export default function DashboardPage() {
  const [status, setStatus] = useState<
    "idle" | "uploading" | "processing" | "done" | "error"
  >("idle");
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<CSVResult | null>(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState<"line" | "bar" | "table">("line");
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Drop zone
  const onDrop = useCallback(async (accepted: File[]) => {
    const file = accepted[0];
    if (!file) return;

    setStatus("uploading");
    setError("");
    setResult(null);
    setProgress(0);

    try {
      const fd = new FormData();
      fd.append("file", file);

      const { data } = await axios.post(`${API}/csv/upload`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      const uploadId: string = data.upload_id;
      setStatus("processing");

      // Poll status
      pollRef.current = setInterval(async () => {
        try {
          const { data: st } = await axios.get(`${API}/csv/status/${uploadId}`);
          setProgress(st.progress_pct ?? 0);

          if (st.status === "complete") {
            clearInterval(pollRef.current!);
            const { data: res } = await axios.get(
              `${API}/csv/result/${uploadId}`,
            );
            setResult(res);
            setStatus("done");
          } else if (st.status === "error") {
            clearInterval(pollRef.current!);
            setError(st.error ?? "Processing failed");
            setStatus("error");
          }
        } catch {
          // keep polling
        }
      }, 1500);
    } catch (e: unknown) {
      const msg = axios.isAxiosError(e)
        ? e.response?.data?.detail
        : "Upload failed";
      setError(String(msg));
      setStatus("error");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "text/csv": [".csv"] },
    maxFiles: 1,
    disabled: status === "uploading" || status === "processing",
  });

  // Derived chart data
  const lineData = result ? toRechartsData(result.data_series) : [];
  const barData = result ? toRechartsData(result.category_series ?? []) : [];

  // Render
  return (
    <main className="min-h-screen p-6 md:p-10 space-y-8">
      {/* Header */}
      <header className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-brand-500 grid place-items-center text-white font-bold text-lg">
          A
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            Insight AI
          </h1>
          <p className="text-sm text-slate-400">
            Upload a CSV → instant chart visualisation
          </p>
        </div>
      </header>

      {/* Drop zone */}
      <section
        {...getRootProps()}
        className={`
          border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all
          ${isDragActive ? "border-brand-500 bg-brand-500/10" : "border-slate-700 hover:border-slate-500"}
          ${status === "uploading" || status === "processing" ? "pointer-events-none opacity-60" : ""}
        `}
      >
        <input {...getInputProps()} />
        <p className="text-4xl mb-3">📂</p>
        {isDragActive ? (
          <p className="text-brand-500 font-semibold">Drop it here…</p>
        ) : (
          <p className="text-slate-300">
            Drag &amp; drop a <span className="font-semibold">.csv</span> file,
            or click to select
          </p>
        )}
        <p className="text-xs text-slate-500 mt-1">
          Up to {process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? "200"} MB
        </p>
      </section>

      {/* Progress / status */}
      {(status === "uploading" || status === "processing") && (
        <div className="space-y-2">
          <p className="text-sm text-slate-400 capitalize">{status}…</p>
          <div className="w-full bg-slate-800 rounded-full h-2">
            <div
              className="bg-brand-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${status === "uploading" ? 10 : progress}%` }}
            />
          </div>
          <p className="text-xs text-slate-500">
            {status === "uploading"
              ? "Uploading file"
              : `${progress}% processed`}
          </p>
        </div>
      )}

      {status === "error" && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4 text-red-300 text-sm">
          ⚠ {error}
        </div>
      )}

      {/* Results */}
      {result && (
        <section className="space-y-6">
          {/* Stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { label: "Rows", value: result.row_count.toLocaleString() },
              { label: "Columns", value: result.col_count },
              { label: "File", value: result.filename },
              {
                label: "Processed",
                value: new Date(result.processed_at).toLocaleTimeString(),
              },
            ].map(({ label, value }) => (
              <div
                key={label}
                className="bg-slate-900 border border-slate-800 rounded-xl p-4"
              >
                <p className="text-xs text-slate-500 uppercase tracking-widest">
                  {label}
                </p>
                <p className="text-lg font-semibold truncate mt-1">{value}</p>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex gap-2">
            {(["line", "bar", "table"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setActiveTab(t)}
                className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors
                  ${activeTab === t ? "bg-brand-500 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
              >
                {t === "line" ? "📈 Line" : t === "bar" ? "📊 Bar" : "🗂 Table"}
              </button>
            ))}
          </div>

          {/* Line chart */}
          {activeTab === "line" && result.data_series.length > 0 && (
            <ChartCard title="Numeric Series">
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={lineData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="x" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      background: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 8,
                    }}
                  />
                  <Legend />
                  {result.data_series.map((s, i) => (
                    <Line
                      key={s.name}
                      type="monotone"
                      dataKey={s.name}
                      stroke={COLORS[i % COLORS.length]}
                      dot={false}
                      strokeWidth={2}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* Bar chart */}
          {activeTab === "bar" && (result.category_series?.length ?? 0) > 0 && (
            <ChartCard title="Category Distribution">
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={barData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                  <XAxis dataKey="x" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      background: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 8,
                    }}
                  />
                  <Legend />
                  {(result.category_series ?? []).map((s, i) => (
                    <Bar
                      key={s.name}
                      dataKey={s.name}
                      fill={COLORS[i % COLORS.length]}
                      radius={[4, 4, 0, 0]}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          )}

          {/* Sample table */}
          {activeTab === "table" && (
            <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-800">
                    {result.columns.map((c) => (
                      <th
                        key={c}
                        className="px-4 py-3 text-left text-xs text-slate-400 font-medium whitespace-nowrap"
                      >
                        {c}
                        <span className="ml-1 text-slate-600">
                          ({result.dtypes[c]})
                        </span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {result.sample_rows.map((row, i) => (
                    <tr
                      key={i}
                      className="border-b border-slate-800/50 hover:bg-slate-800/40"
                    >
                      {result.columns.map((c) => (
                        <td
                          key={c}
                          className="px-4 py-2 text-slate-300 whitespace-nowrap"
                        >
                          {row[c] == null ? (
                            <span className="text-slate-600 italic">null</span>
                          ) : (
                            String(row[c])
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-slate-600 px-4 py-2">
                Showing first 10 of {result.row_count.toLocaleString()} rows
              </p>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function ChartCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5">
      <h2 className="text-sm font-semibold text-slate-400 mb-4 uppercase tracking-widest">
        {title}
      </h2>
      {children}
    </div>
  );
}