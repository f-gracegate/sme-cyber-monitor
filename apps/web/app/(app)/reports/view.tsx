"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Download, FileSpreadsheet, FileText } from "lucide-react";
import { useState } from "react";
import { Pager } from "@/components/pager";
import { useToast } from "@/components/providers";
import { useOrgKey } from "@/components/session";
import {
  Badge,
  Button,
  Callout,
  Card,
  CardHeader,
  EmptyState,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
} from "@/components/ui";
import { api, downloadFile, errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import type { Page, ReportItem, ReportTypeInfo } from "@/lib/types";
import { useUrlState } from "@/lib/use-url-state";

const PAGE_SIZE = 25;

const DESCRIPTIONS: Record<string, string> = {
  executive: "One-page posture summary for owners and management: score, trend, top risks and progress.",
  asset_inventory: "Every asset with type, owner, criticality and monitoring status.",
  endpoint_health: "Devices, agent status, protection and patch health.",
  findings: "Open and recently resolved findings with severity and recommendations.",
  incidents: "Incidents in the period with timings, outcomes and lessons learned.",
  remediation: "Tasks, owners, deadlines and on-time performance.",
  coverage: "What is and isn't monitored, and where data is stale.",
};

const isoDay = (d: Date) => d.toISOString().slice(0, 10);

export function View() {
  const url = useUrlState();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const today = new Date();
  const [type, setType] = useState("executive");
  const [format, setFormat] = useState<"pdf" | "csv">("pdf");
  const [start, setStart] = useState(isoDay(new Date(today.getTime() - 30 * 86_400_000)));
  const [end, setEnd] = useState(isoDay(today));

  const types = useQuery({
    queryKey: useOrgKey("report-types"),
    queryFn: () => api<ReportTypeInfo[]>("/reports/types"),
    staleTime: Infinity,
  });
  const { data, isPending } = useQuery({
    queryKey: useOrgKey("reports", { page: url.page }),
    queryFn: () => api<Page<ReportItem>>("/reports", { query: { page: url.page, page_size: PAGE_SIZE } }),
    placeholderData: keepPreviousData,
  });

  const csvAllowed = types.data?.find((t) => t.value === type)?.csv ?? false;
  const generate = useMutation({
    mutationFn: () =>
      api<ReportItem>("/reports", {
        method: "POST",
        body: {
          report_type: type,
          format: csvAllowed ? format : "pdf",
          period_start: new Date(`${start}T00:00:00`).toISOString(),
          period_end: new Date(`${end}T23:59:59`).toISOString(),
        },
      }),
    onSuccess: (r) => {
      queryClient.invalidateQueries({ queryKey: [...orgKey, "reports"] });
      toast("success", "Report ready.");
      download(r);
    },
  });
  const download = (r: ReportItem) =>
    downloadFile(`/reports/${r.id}/download`, `${r.report_type}.${r.format}`).catch((e) =>
      toast("error", errorMessage(e)),
    );

  return (
    <>
      <PageHeader
        title="Reports"
        description="Evidence for management, insurers, clients and auditors. An executive summary is generated automatically on the 1st of each month and emailed to owners and admins."
      />
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardHeader title="Generate a report" />
          <form
            className="space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              generate.mutate();
            }}
          >
            {generate.isError && <Callout tone="critical">{errorMessage(generate.error)}</Callout>}
            <Field label="Report" htmlFor="rep-type" hint={DESCRIPTIONS[type]}>
              <Select id="rep-type" value={type} onChange={(e) => setType(e.target.value)}>
                {(types.data ?? []).map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="From" htmlFor="rep-start">
                <Input id="rep-start" type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)} />
              </Field>
              <Field label="To" htmlFor="rep-end">
                <Input id="rep-end" type="date" value={end} min={start} max={isoDay(today)} onChange={(e) => setEnd(e.target.value)} />
              </Field>
            </div>
            <Field label="Format" htmlFor="rep-format" hint={csvAllowed ? "CSV opens in Excel or Google Sheets." : "This report is PDF only."}>
              <Select id="rep-format" value={csvAllowed ? format : "pdf"} disabled={!csvAllowed} onChange={(e) => setFormat(e.target.value as "pdf" | "csv")}>
                <option value="pdf">PDF</option>
                <option value="csv">CSV spreadsheet</option>
              </Select>
            </Field>
            <Button type="submit" loading={generate.isPending} className="w-full">
              Generate and download
            </Button>
          </form>
        </Card>

        <Card padded={false} className="lg:col-span-2">
          <div className="p-5 pb-1">
            <CardHeader title="Report history" description="Reports are stored encrypted. Every download is recorded in the audit log." />
          </div>
          {isPending ? (
            <div className="p-4">
              <Skeleton className="h-48" />
            </div>
          ) : !data?.items.length ? (
            <EmptyState icon={<FileText className="size-5" />} title="No reports yet" description="Generate your first report, or wait for the monthly executive summary." />
          ) : (
            <>
              <ul className="divide-y divide-border border-t border-border">
                {data.items.map((r) => (
                  <li key={r.id} className="flex items-center gap-3 px-5 py-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-muted">
                      {r.format === "csv" ? <FileSpreadsheet className="size-4" /> : <FileText className="size-4" />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-medium text-fg">{r.type_label}</span>
                        <Badge>{r.format.toUpperCase()}</Badge>
                        {r.scheduled && (
                          <Badge tone="info">
                            <CalendarClock className="size-3" /> Monthly
                          </Badge>
                        )}
                      </span>
                      <span className="mt-0.5 block text-[13px] text-muted">
                        {formatDate(r.period_start)} – {formatDate(r.period_end)} · {r.created_by_name ?? "Scheduled"} · {timeAgo(r.created_at)}
                      </span>
                    </span>
                    <Button size="sm" variant="secondary" onClick={() => download(r)} disabled={r.status !== "ready"} aria-label={`Download ${r.type_label}`}>
                      <Download className="size-4" />
                    </Button>
                  </li>
                ))}
              </ul>
              <Pager page={url.page} total={data.total} pageSize={PAGE_SIZE} noun={["report", "reports"]} onPage={(p) => url.set({ page: String(p) }, true)} />
            </>
          )}
        </Card>
      </div>
    </>
  );
}
