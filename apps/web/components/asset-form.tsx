"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { Dialog } from "@/components/dialog";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import { Button, Callout, Field, Input, Select, Textarea } from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { ASSET_TYPES, CATEGORIES, CRITICALITY, IDENTIFIER_HINTS } from "@/lib/labels";
import type { AssetDetail, Department, Member } from "@/lib/types";

type FormState = {
  name: string;
  type: string;
  identifier: string;
  criticality: string;
  department_id: string;
  owner_user_id: string;
  technology: string;
  location: string;
  notes: string;
};

const EMPTY: FormState = {
  name: "",
  type: "website",
  identifier: "",
  criticality: "medium",
  department_id: "",
  owner_user_id: "",
  technology: "",
  location: "",
  notes: "",
};

export function useOrgLookups() {
  const { orgId, can } = useSession();
  const departments = useQuery({
    queryKey: useOrgKey("departments"),
    queryFn: () => api<Department[]>(`/organisations/${orgId}/departments`),
  });
  const members = useQuery({
    queryKey: useOrgKey("members"),
    queryFn: () => api<Member[]>(`/organisations/${orgId}/members`),
    enabled: can("members:read"),
  });
  return { departments: departments.data ?? [], members: members.data ?? [] };
}

export function AssetFormDialog({
  open,
  onClose,
  asset,
  onSaved,
}: {
  open: boolean;
  onClose: () => void;
  asset?: AssetDetail;
  onSaved?: (asset: AssetDetail) => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const { departments, members } = useOrgLookups();
  const editing = Boolean(asset);
  const [form, setForm] = useState<FormState>(() =>
    asset
      ? {
          name: asset.name,
          type: asset.type,
          identifier: asset.identifier,
          criticality: asset.criticality,
          department_id: asset.department_id ?? "",
          owner_user_id: asset.owner_user_id ?? "",
          technology: asset.technology ?? "",
          location: asset.location ?? "",
          notes: asset.notes ?? "",
        }
      : EMPTY,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});

  const set = (key: keyof FormState) => (value: string) => setForm((f) => ({ ...f, [key]: value }));

  const save = useMutation({
    mutationFn: () => {
      const body = {
        name: form.name,
        identifier: form.identifier,
        criticality: form.criticality,
        department_id: form.department_id || null,
        owner_user_id: form.owner_user_id || null,
        technology: form.technology || null,
        location: form.location || null,
        notes: form.notes || null,
      };
      return editing
        ? api<AssetDetail>(`/assets/${asset!.id}`, { method: "PATCH", body })
        : api<AssetDetail>("/assets", { method: "POST", body: { ...body, type: form.type } });
    },
    onSuccess: (saved) => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", editing ? "Asset updated." : `${saved.name} registered.`);
      if (onSaved) onSaved(saved);
      else onClose();
    },
    onError: (err) => {
      if (err instanceof ApiError) setErrors(err.fieldErrors());
    },
  });

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    setErrors({});
    save.mutate();
  }

  const hint = IDENTIFIER_HINTS[form.type] ?? IDENTIFIER_HINTS.server;
  const external = form.type === "website" || form.type === "domain";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      wide
      title={editing ? "Edit asset" : "Add an asset"}
      description={
        editing
          ? undefined
          : "Register something your business owns or is responsible for protecting."
      }
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="asset-form" loading={save.isPending}>
            {editing ? "Save changes" : "Add asset"}
          </Button>
        </>
      }
    >
      <form id="asset-form" onSubmit={onSubmit} className="grid gap-4 sm:grid-cols-2" noValidate>
        {save.isError && !Object.keys(errors).length && (
          <div className="sm:col-span-2">
            <Callout tone="critical">{errorMessage(save.error)}</Callout>
          </div>
        )}
        <Field label="Asset type" htmlFor="type" className="sm:col-span-2">
          <Select
            id="type"
            value={form.type}
            onChange={(e) => set("type")(e.target.value)}
            disabled={editing}
          >
            {CATEGORIES.map((c) => (
              <optgroup key={c.value} label={c.label}>
                {ASSET_TYPES.filter((t) => t.category === c.value).map((t) => (
                  <option key={t.value} value={t.value}>
                    {t.label}
                  </option>
                ))}
              </optgroup>
            ))}
          </Select>
        </Field>
        <Field label="Name" htmlFor="name" error={errors.name}>
          <Input
            id="name"
            value={form.name}
            onChange={(e) => set("name")(e.target.value)}
            placeholder="e.g. Company website"
            invalid={!!errors.name}
            autoFocus
          />
        </Field>
        <Field
          label={hint.label}
          htmlFor="identifier"
          error={errors.identifier}
          hint={
            editing && external
              ? "Changing this requires verifying ownership again."
              : undefined
          }
        >
          <Input
            id="identifier"
            value={form.identifier}
            onChange={(e) => set("identifier")(e.target.value)}
            placeholder={hint.placeholder}
            invalid={!!errors.identifier}
            spellCheck={false}
            autoCapitalize="off"
          />
        </Field>
        <Field
          label="Business criticality"
          htmlFor="criticality"
          hint="How badly would the business be hurt if this were unavailable or compromised?"
        >
          <Select
            id="criticality"
            value={form.criticality}
            onChange={(e) => set("criticality")(e.target.value)}
          >
            {CRITICALITY.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Operating system or technology" htmlFor="technology" optional>
          <Input
            id="technology"
            value={form.technology}
            onChange={(e) => set("technology")(e.target.value)}
            placeholder={external ? "e.g. WordPress, Shopify" : "e.g. Windows 11 Pro"}
          />
        </Field>
        <Field label="Department" htmlFor="department" optional error={errors.department_id}>
          <Select
            id="department"
            value={form.department_id}
            onChange={(e) => set("department_id")(e.target.value)}
          >
            <option value="">No department</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Owner" htmlFor="owner" optional error={errors.owner_user_id}>
          <Select
            id="owner"
            value={form.owner_user_id}
            onChange={(e) => set("owner_user_id")(e.target.value)}
          >
            <option value="">No owner</option>
            {members.map((m) => (
              <option key={m.user_id} value={m.user_id}>
                {m.full_name || m.email}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Location" htmlFor="location" optional className="sm:col-span-2">
          <Input
            id="location"
            value={form.location}
            onChange={(e) => set("location")(e.target.value)}
            placeholder="e.g. Head office, Osu"
          />
        </Field>
        <Field label="Notes" htmlFor="notes" optional className="sm:col-span-2">
          <Textarea
            id="notes"
            value={form.notes}
            onChange={(e) => set("notes")(e.target.value)}
            rows={3}
          />
        </Field>
      </form>
    </Dialog>
  );
}
