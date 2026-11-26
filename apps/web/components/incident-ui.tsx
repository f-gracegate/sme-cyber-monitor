"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, CircleCheck, Link2, Wrench } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { SeverityBadge } from "@/components/monitoring-ui";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Badge, Button, Callout, Field, Input, Select, Textarea, cn } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { INCIDENT_STATUS, SEVERITIES, TASK_KIND, TASK_STATUS } from "@/lib/labels";
import type { Member, Task } from "@/lib/types";

export function IncidentStatusBadge({ status }: { status: string }) {
  const meta = INCIDENT_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

export function TaskStatusBadge({ status }: { status: string }) {
  const meta = TASK_STATUS[status] ?? { label: status, tone: "neutral" as const };
  return <Badge tone={meta.tone}>{meta.label}</Badge>;
}

/** Active team members who can be given incidents and tasks. */
export function useAssignees() {
  const { orgId, can } = useSession();
  const { data } = useQuery({
    queryKey: useOrgKey("members"),
    queryFn: () => api<Member[]>(`/organisations/${orgId}/members`),
    enabled: !!orgId && can("members:read"),
    staleTime: 60_000,
  });
  return (data ?? []).filter((m) => m.status === "active");
}

export function AssigneeSelect({
  id,
  value,
  onChange,
  placeholder = "Unassigned",
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const people = useAssignees();
  return (
    <Select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{placeholder}</option>
      {people.map((m) => (
        <option key={m.user_id} value={m.user_id}>
          {m.full_name || m.email} · {m.role_label}
        </option>
      ))}
    </Select>
  );
}

const toIsoDate = (d: string) => (d ? new Date(`${d}T17:00:00`).toISOString() : undefined);

/** Create a remediation task for a finding, or a containment/recovery task on an incident. */
export function TaskDialog({
  open,
  onClose,
  findingId,
  incidentId,
  defaultTitle = "",
}: {
  open: boolean;
  onClose: () => void;
  findingId?: string;
  incidentId?: string;
  defaultTitle?: string;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [title, setTitle] = useState(defaultTitle);
  const [kind, setKind] = useState(incidentId && !findingId ? "containment" : "remediation");
  const [priority, setPriority] = useState("");
  const [assignee, setAssignee] = useState("");
  const [due, setDue] = useState("");
  const [description, setDescription] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api<Task>("/remediation-tasks", {
        method: "POST",
        body: {
          title: title.trim() || undefined,
          description: description.trim() || undefined,
          kind,
          priority: priority || undefined,
          finding_id: findingId,
          incident_id: incidentId,
          assignee_id: assignee || undefined,
          due_at: toIsoDate(due),
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", assignee ? "Task created and assigned." : "Task created.");
      onClose();
    },
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={findingId ? "Assign a fix" : "Add a task"}
      description={
        findingId
          ? "Track who fixes this and by when. The task is verified automatically when monitoring confirms the problem is gone."
          : "Containment stops the damage spreading; recovery gets things back to normal."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button loading={create.isPending} onClick={() => create.mutate()} disabled={!findingId && !title.trim()}>
            Create task
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {create.isError && <Callout tone="critical">{errorMessage(create.error)}</Callout>}
        <Field label="Task" htmlFor="task-title" optional={!!findingId} hint={findingId ? "Leave blank to use the finding's recommendation." : undefined}>
          <Input id="task-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} />
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          {!findingId && (
            <Field label="Type" htmlFor="task-kind">
              <Select id="task-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
                {Object.entries(TASK_KIND).map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </Select>
            </Field>
          )}
          <Field label="Priority" htmlFor="task-priority" optional>
            <Select id="task-priority" value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="">{findingId ? "Same as finding" : "Same as incident"}</option>
              {SEVERITIES.filter((s) => s.value !== "informational").map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Assign to" htmlFor="task-assignee" optional>
            <AssigneeSelect id="task-assignee" value={assignee} onChange={setAssignee} />
          </Field>
          <Field label="Due" htmlFor="task-due" optional hint="Defaults by priority (critical 1 day, high 7, medium 30).">
            <Input id="task-due" type="date" value={due} onChange={(e) => setDue(e.target.value)} />
          </Field>
        </div>
        <Field label="Details" htmlFor="task-desc" optional>
          <Textarea id="task-desc" rows={3} value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
      </div>
    </Dialog>
  );
}

/** One task with inline progress controls (managers: any status; assignees: progress only). */
export function TaskRow({ task, showContext = true }: { task: Task; showContext?: boolean }) {
  const { me, can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const manage = can("remediation:manage");
  const mine = task.assignee?.id === me.user.id;

  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Task>(`/remediation-tasks/${task.id}`, { method: "PATCH", body }),
    onSuccess: (t) => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", t.status === "verified" ? "Task verified." : "Task updated.");
    },
    onError: (e) => toast("error", errorMessage(e)),
  });

  const closed = task.status === "verified" || task.status === "cancelled";
  const actions: { status: string; label: string }[] = [];
  if (!closed && (manage || mine)) {
    if (task.status === "open") actions.push({ status: "in_progress", label: "Start" });
    if (task.status === "open" || task.status === "in_progress") actions.push({ status: "done", label: "Mark done" });
    if (manage && task.status === "done") actions.push({ status: "verified", label: "Verify" });
    if (manage && task.status === "done") actions.push({ status: "in_progress", label: "Reopen" });
  }

  return (
    <li className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn("font-medium text-fg", closed && "text-muted line-through decoration-subtle")}>{task.title}</span>
          <SeverityBadge severity={task.priority} />
          <TaskStatusBadge status={task.status} />
          {task.kind !== "remediation" && <Badge>{TASK_KIND[task.kind]}</Badge>}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
          <span>{task.assignee ? task.assignee.name : <span className="text-high-text">Unassigned</span>}</span>
          {task.due_at && (
            <span className={cn("inline-flex items-center gap-1", task.overdue && "font-medium text-critical-text")}>
              <CalendarClock className="size-3.5" />
              {task.overdue ? "Overdue since" : "Due"} {formatDate(task.due_at)}
            </span>
          )}
          {task.verified_at && (
            <span className="inline-flex items-center gap-1 text-success-text">
              <CircleCheck className="size-3.5" />
              Verified {task.verification === "monitoring" ? "by monitoring" : "manually"} {formatDate(task.verified_at)}
            </span>
          )}
          {showContext && task.finding_id && (
            <Link href={`/findings/${task.finding_id}`} className="inline-flex items-center gap-1 hover:text-fg">
              <Wrench className="size-3.5" /> Finding{task.asset_name ? ` on ${task.asset_name}` : ""}
            </Link>
          )}
          {showContext && task.incident_id && (
            <Link href={`/incidents/${task.incident_id}`} className="inline-flex items-center gap-1 hover:text-fg">
              <Link2 className="size-3.5" /> {task.incident_reference}
            </Link>
          )}
        </div>
        {task.note && <p className="mt-1 text-[13px] text-muted italic">&ldquo;{task.note}&rdquo;</p>}
      </div>
      {actions.length > 0 && (
        <div className="flex shrink-0 gap-2">
          {actions.map((a) => (
            <Button
              key={a.status + a.label}
              size="sm"
              variant={a.status === "done" || a.status === "verified" ? "primary" : "secondary"}
              loading={update.isPending && update.variables?.status === a.status}
              onClick={() => update.mutate({ status: a.status })}
            >
              {a.label}
            </Button>
          ))}
        </div>
      )}
    </li>
  );
}

export const incidentStatusOptions = Object.entries(INCIDENT_STATUS).map(([value, m]) => ({
  value,
  label: m.label,
}));
