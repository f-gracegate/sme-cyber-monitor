"use client";

import { useState, type FormEvent, type ReactNode } from "react";
import { Callout, Field, Input, Select } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { INDUSTRIES, SIZES } from "@/lib/labels";
import type { Organisation } from "@/lib/types";

export type OrgFormValues = {
  name: string;
  industry: string;
  size: string;
  phone: string;
  address: string;
  website: string;
  timezone: string;
};

export function toOrgForm(org?: Organisation): OrgFormValues {
  return {
    name: org?.name ?? "",
    industry: org?.industry ?? "",
    size: org?.size ?? "",
    phone: org?.phone ?? "",
    address: org?.address ?? "",
    website: org?.website ?? "",
    timezone: org?.timezone ?? "Africa/Accra",
  };
}

export function toOrgPayload(v: OrgFormValues) {
  return {
    name: v.name,
    industry: v.industry || null,
    size: v.size || null,
    phone: v.phone || null,
    address: v.address || null,
    website: v.website || null,
    timezone: v.timezone,
  };
}

export function OrgForm({
  initial,
  onSubmit,
  error,
  readOnly,
  footer,
}: {
  initial: OrgFormValues;
  onSubmit: (values: OrgFormValues) => void;
  error: unknown;
  readOnly?: boolean;
  footer: ReactNode;
}) {
  const [v, setV] = useState(initial);
  const set = (k: keyof OrgFormValues) => (value: string) => setV((s) => ({ ...s, [k]: value }));
  const errors = error instanceof ApiError ? error.fieldErrors() : {};

  return (
    <form
      onSubmit={(e: FormEvent) => {
        e.preventDefault();
        onSubmit(v);
      }}
      className="grid gap-4 sm:grid-cols-2"
      noValidate
    >
      {error instanceof ApiError && !Object.keys(errors).length ? (
        <div className="sm:col-span-2">
          <Callout tone="critical">{error.message}</Callout>
        </div>
      ) : null}
      <Field label="Business name" htmlFor="org-name" error={errors.name} className="sm:col-span-2">
        <Input
          id="org-name"
          value={v.name}
          onChange={(e) => set("name")(e.target.value)}
          disabled={readOnly}
          invalid={!!errors.name}
          autoComplete="organization"
        />
      </Field>
      <Field label="Industry" htmlFor="org-industry" optional error={errors.industry}>
        <Select
          id="org-industry"
          value={v.industry}
          onChange={(e) => set("industry")(e.target.value)}
          disabled={readOnly}
        >
          <option value="">Select…</option>
          {INDUSTRIES.map((i) => (
            <option key={i.value} value={i.value}>
              {i.label}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Number of staff" htmlFor="org-size" optional error={errors.size}>
        <Select
          id="org-size"
          value={v.size}
          onChange={(e) => set("size")(e.target.value)}
          disabled={readOnly}
        >
          <option value="">Select…</option>
          {SIZES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Phone" htmlFor="org-phone" optional>
        <Input
          id="org-phone"
          type="tel"
          value={v.phone}
          onChange={(e) => set("phone")(e.target.value)}
          placeholder="+233 …"
          disabled={readOnly}
          autoComplete="tel"
        />
      </Field>
      <Field label="Website" htmlFor="org-website" optional>
        <Input
          id="org-website"
          value={v.website}
          onChange={(e) => set("website")(e.target.value)}
          placeholder="www.yourbusiness.com.gh"
          disabled={readOnly}
        />
      </Field>
      <Field label="Address" htmlFor="org-address" optional className="sm:col-span-2">
        <Input
          id="org-address"
          value={v.address}
          onChange={(e) => set("address")(e.target.value)}
          placeholder="Street, area, city"
          disabled={readOnly}
          autoComplete="street-address"
        />
      </Field>
      <Field label="Time zone" htmlFor="org-tz" hint="Used for reports and schedules.">
        <Select
          id="org-tz"
          value={v.timezone}
          onChange={(e) => set("timezone")(e.target.value)}
          disabled={readOnly}
        >
          {["Africa/Accra", "Africa/Lagos", "Africa/Abidjan", "Africa/Lome", "Europe/London", "UTC"].map(
            (tz) => (
              <option key={tz} value={tz}>
                {tz.replace("_", " ")}
              </option>
            ),
          )}
        </Select>
      </Field>
      <div className="flex items-end justify-end gap-2 sm:col-span-2">{footer}</div>
    </form>
  );
}
