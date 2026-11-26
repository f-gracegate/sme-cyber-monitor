"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Callout, Card, CardHeader, EmptyState, Input, Skeleton } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";
import type { Department } from "@/lib/types";

export default function DepartmentsPage() {
  const { orgId, can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("departments");
  const [name, setName] = useState("");
  const { data, isPending } = useQuery({
    queryKey: key,
    queryFn: () => api<Department[]>(`/organisations/${orgId}/departments`),
  });
  const create = useMutation({
    mutationFn: () =>
      api<Department>(`/organisations/${orgId}/departments`, { method: "POST", body: { name } }),
    onSuccess: () => {
      setName("");
      queryClient.invalidateQueries({ queryKey: key });
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) =>
      api(`/organisations/${orgId}/departments/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key.slice(0, 2) });
      toast("success", "Department deleted.");
    },
    onError: (err) => toast("error", errorMessage(err)),
  });
  const editable = can("departments:manage");

  return (
    <Card>
      <CardHeader
        title="Departments"
        description="Group people and assets so reports and responsibilities are clear."
      />
      {editable && (
        <form
          className="mb-5 flex gap-2"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Finance"
            aria-label="New department name"
            className="max-w-sm"
          />
          <Button type="submit" loading={create.isPending} disabled={!name.trim()}>
            <Plus className="size-4" /> Add
          </Button>
        </form>
      )}
      {create.isError && (
        <div className="mb-4">
          <Callout tone="critical">{errorMessage(create.error)}</Callout>
        </div>
      )}
      {isPending ? (
        <Skeleton className="h-32" />
      ) : !data?.length ? (
        <EmptyState title="No departments yet" description="Add the teams in your business, such as Finance, Operations or IT." />
      ) : (
        <ul className="divide-y divide-border rounded-[var(--radius-control)] border border-border">
          {data.map((d) => (
            <li key={d.id} className="flex items-center justify-between px-4 py-3 text-sm">
              <span className="font-medium">{d.name}</span>
              {editable && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => remove.mutate(d.id)}
                  aria-label={`Delete ${d.name}`}
                >
                  <Trash2 className="size-4" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      {editable && data && data.length > 0 && (
        <p className="mt-3 text-xs text-subtle">
          Deleting a department keeps its assets and members; they just become unassigned.
        </p>
      )}
    </Card>
  );
}
