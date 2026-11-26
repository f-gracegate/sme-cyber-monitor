"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { OrgForm, toOrgForm, toOrgPayload } from "@/components/org-form";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Card, CardHeader, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { Organisation } from "@/lib/types";

export default function BusinessProfilePage() {
  const { orgId, can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const key = useOrgKey("organisation");
  const { data } = useQuery({
    queryKey: key,
    queryFn: () => api<Organisation>(`/organisations/${orgId}`),
  });
  const save = useMutation({
    mutationFn: (body: object) =>
      api<Organisation>(`/organisations/${orgId}`, { method: "PATCH", body }),
    onSuccess: (org) => {
      queryClient.setQueryData(key, org);
      queryClient.invalidateQueries({ queryKey: ["me"] });
      toast("success", "Business profile saved.");
    },
  });
  const editable = can("org:update");

  return (
    <Card>
      <CardHeader
        title="Business profile"
        description={
          editable
            ? "Shown on reports and used to tailor recommendations."
            : "Only owners and administrators can change these details."
        }
      />
      {!data ? (
        <Skeleton className="h-72" />
      ) : (
        <OrgForm
          key={data.id}
          initial={toOrgForm(data)}
          readOnly={!editable}
          error={save.error}
          onSubmit={(v) => save.mutate(toOrgPayload(v))}
          footer={editable && <Button type="submit" loading={save.isPending}>Save changes</Button>}
        />
      )}
    </Card>
  );
}
