"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Clock, ShieldCheck, ShieldOff, UserMinus, UserPlus, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { CopyField } from "@/components/copy-field";
import { Dialog } from "@/components/dialog";
import { useToast } from "@/components/providers";
import { useOrgKey, useSession } from "@/components/session";
import {
  Avatar,
  Badge,
  Button,
  Callout,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  Skeleton,
  Table,
  Td,
  Th,
} from "@/components/ui";
import { api, ApiError, errorMessage } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";
import type { Department, Invitation, Member, RoleInfo } from "@/lib/types";

const ROLE_HELP: Record<string, string> = {
  owner: "Full control, including billing and other owners.",
  admin: "Manages people, assets, monitoring and settings.",
  security_analyst: "Investigates alerts, reviews findings and manages incidents.",
  it_admin: "Manages endpoints, servers, agents and network collectors.",
  auditor: "Read-only access to reports, findings and audit records.",
  executive: "High-level security posture, reports and trends.",
  employee: "Reports incidents and sees tasks assigned to them.",
};

function InviteDialog({
  open,
  onClose,
  roles,
}: {
  open: boolean;
  onClose: () => void;
  roles: RoleInfo[];
}) {
  const { orgId, membership } = useSession();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("it_admin");
  const [link, setLink] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const assignable = roles.filter((r) => r.value !== "owner" || membership?.role === "owner");

  const invite = useMutation({
    mutationFn: () =>
      api<{ invite_url: string }>(`/organisations/${orgId}/invitations`, {
        method: "POST",
        body: { email, role },
      }),
    onSuccess: (res) => {
      setLink(res.invite_url);
      queryClient.invalidateQueries({ queryKey: [...orgKey, "invitations"] });
      queryClient.invalidateQueries({ queryKey: [...orgKey, "overview"] });
    },
    onError: (err) => {
      if (err instanceof ApiError) setErrors(err.fieldErrors());
    },
  });

  function close() {
    setEmail("");
    setLink(null);
    setErrors({});
    invite.reset();
    onClose();
  }

  return (
    <Dialog
      open={open}
      onClose={close}
      title={link ? "Invitation sent" : "Invite a team member"}
      description={
        link
          ? `We've emailed ${email}. You can also share this link with them directly. It works once and expires in 7 days.`
          : "They'll get an email with a link to join your organisation."
      }
      footer={
        link ? (
          <Button onClick={close}>Done</Button>
        ) : (
          <>
            <Button variant="secondary" onClick={close}>
              Cancel
            </Button>
            <Button type="submit" form="invite-form" loading={invite.isPending} disabled={!email}>
              Send invitation
            </Button>
          </>
        )
      }
    >
      {link ? (
        <CopyField label="Invitation link" value={link} />
      ) : (
        <form
          id="invite-form"
          className="space-y-4"
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            setErrors({});
            invite.mutate();
          }}
          noValidate
        >
          {invite.isError && !errors.email && (
            <Callout tone="critical">{errorMessage(invite.error)}</Callout>
          )}
          <Field label="Email address" htmlFor="invite-email" error={errors.email}>
            <Input
              id="invite-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              invalid={!!errors.email}
              autoFocus
            />
          </Field>
          <Field label="Role" htmlFor="invite-role" hint={ROLE_HELP[role]}>
            <Select id="invite-role" value={role} onChange={(e) => setRole(e.target.value)}>
              {assignable.map((r) => (
                <option key={r.value} value={r.value}>
                  {r.label}
                </option>
              ))}
            </Select>
          </Field>
        </form>
      )}
    </Dialog>
  );
}

function MemberRow({
  m,
  roles,
  departments,
}: {
  m: Member;
  roles: RoleInfo[];
  departments: Department[];
}) {
  const { orgId, can, membership } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [confirmRemove, setConfirmRemove] = useState(false);
  const canManage =
    can("members:manage") && !m.is_you && (m.role !== "owner" || membership?.role === "owner");

  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) =>
      api<Member>(`/organisations/${orgId}/members/${m.id}`, { method: "PATCH", body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", "Member updated.");
    },
    onError: (err) => toast("error", errorMessage(err)),
  });
  const remove = useMutation({
    mutationFn: () => api(`/organisations/${orgId}/members/${m.id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: orgKey });
      toast("success", `${m.full_name || m.email} removed.`);
      setConfirmRemove(false);
    },
    onError: (err) => toast("error", errorMessage(err)),
  });
  const assignable = roles.filter((r) => r.value !== "owner" || membership?.role === "owner");

  return (
    <tr className={m.status === "suspended" ? "opacity-60" : undefined}>
      <Td>
        <div className="flex items-center gap-3">
          <Avatar name={m.full_name || m.email} />
          <div className="min-w-0">
            <p className="truncate font-medium">
              {m.full_name || m.email} {m.is_you && <span className="font-normal text-subtle">(you)</span>}
            </p>
            <p className="truncate text-xs text-subtle">{m.email}</p>
          </div>
        </div>
      </Td>
      <Td>
        {canManage ? (
          <Select
            aria-label={`Role for ${m.email}`}
            value={m.role}
            onChange={(e) => update.mutate({ role: e.target.value })}
            className="h-9 w-52"
          >
            {assignable.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </Select>
        ) : (
          <span className="text-sm">{m.role_label}</span>
        )}
      </Td>
      <Td>
        {canManage ? (
          <Select
            aria-label={`Department for ${m.email}`}
            value={m.department_id ?? ""}
            onChange={(e) =>
              update.mutate(
                e.target.value ? { department_id: e.target.value } : { clear_department: true },
              )
            }
            className="h-9 w-40"
          >
            <option value="">—</option>
            {departments.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name}
              </option>
            ))}
          </Select>
        ) : (
          <span className="text-sm text-muted">{m.department_name ?? "—"}</span>
        )}
      </Td>
      <Td>
        {m.mfa_enabled ? (
          <Badge tone="success">
            <ShieldCheck className="size-3" /> On
          </Badge>
        ) : (
          <Badge tone={["owner", "admin", "it_admin"].includes(m.role) ? "critical" : "warning"}>
            <ShieldOff className="size-3" /> Off
          </Badge>
        )}
      </Td>
      <Td className="text-sm text-muted">
        {m.status === "suspended" ? <Badge tone="warning">Suspended</Badge> : timeAgo(m.last_login_at)}
      </Td>
      <Td className="text-right">
        {canManage && (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() =>
                update.mutate({ status: m.status === "active" ? "suspended" : "active" })
              }
              title={m.status === "active" ? "Suspend access" : "Restore access"}
            >
              <Ban className="size-4" />
              <span className="sr-only">{m.status === "active" ? "Suspend" : "Reactivate"}</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setConfirmRemove(true)} title="Remove">
              <UserMinus className="size-4" />
              <span className="sr-only">Remove</span>
            </Button>
          </div>
        )}
        <Dialog
          open={confirmRemove}
          onClose={() => setConfirmRemove(false)}
          title={`Remove ${m.full_name || m.email}?`}
          description="They lose access to this organisation immediately. Their account and the audit history stay intact."
          footer={
            <>
              <Button variant="secondary" onClick={() => setConfirmRemove(false)}>
                Cancel
              </Button>
              <Button variant="danger" loading={remove.isPending} onClick={() => remove.mutate()}>
                Remove member
              </Button>
            </>
          }
        >
          <p className="text-sm text-muted">You can invite them again later.</p>
        </Dialog>
      </Td>
    </tr>
  );
}

export default function TeamPage() {
  const { orgId, can } = useSession();
  const toast = useToast();
  const queryClient = useQueryClient();
  const orgKey = useOrgKey();
  const [inviting, setInviting] = useState(false);

  const members = useQuery({
    queryKey: [...orgKey, "members"],
    queryFn: () => api<Member[]>(`/organisations/${orgId}/members`),
  });
  const invitations = useQuery({
    queryKey: [...orgKey, "invitations"],
    queryFn: () => api<Invitation[]>(`/organisations/${orgId}/invitations`),
  });
  const roles = useQuery({
    queryKey: ["roles"],
    queryFn: () => api<RoleInfo[]>("/roles", { org: false }),
    staleTime: Infinity,
  });
  const departments = useQuery({
    queryKey: [...orgKey, "departments"],
    queryFn: () => api<Department[]>(`/organisations/${orgId}/departments`),
  });
  const revoke = useMutation({
    mutationFn: (id: string) =>
      api(`/organisations/${orgId}/invitations/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: [...orgKey, "invitations"] });
      toast("success", "Invitation cancelled.");
    },
  });

  const roleLabel = (v: string) => roles.data?.find((r) => r.value === v)?.label ?? v;
  const withoutMfa = (members.data ?? []).filter((m) => !m.mfa_enabled).length;

  return (
    <>
      <PageHeader
        title="Team"
        description="People who can access this organisation's security workspace, and what each of them can do."
        actions={
          can("members:manage") && (
            <Button onClick={() => setInviting(true)}>
              <UserPlus className="size-4" /> Invite member
            </Button>
          )
        }
      />

      {withoutMfa > 0 && (
        <div className="mb-5">
          <Callout tone="warning" icon={<ShieldOff className="size-4" />}>
            {withoutMfa} member{withoutMfa === 1 ? " has" : "s have"} not turned on multi-factor
            authentication. You can require it for everyone in Settings → Security.
          </Callout>
        </div>
      )}

      <Card padded={false}>
        {members.isPending ? (
          <div className="space-y-2 p-4">
            <Skeleton className="h-12" />
            <Skeleton className="h-12" />
          </div>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Member</Th>
                <Th>Role</Th>
                <Th>Department</Th>
                <Th>MFA</Th>
                <Th>Last sign-in</Th>
                <Th>
                  <span className="sr-only">Actions</span>
                </Th>
              </tr>
            </thead>
            <tbody>
              {(members.data ?? []).map((m) => (
                <MemberRow
                  key={m.id}
                  m={m}
                  roles={roles.data ?? []}
                  departments={departments.data ?? []}
                />
              ))}
            </tbody>
          </Table>
        )}
      </Card>

      {(invitations.data?.length ?? 0) > 0 && (
        <Card padded={false} className="mt-6">
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-[15px] font-semibold">Pending invitations</h2>
          </div>
          <ul className="divide-y divide-border">
            {invitations.data!.map((inv) => (
              <li key={inv.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-sm">
                <Clock className="size-4 text-subtle" />
                <span className="min-w-0 flex-1">
                  <span className="font-medium">{inv.email}</span>
                  <span className="text-muted"> · {roleLabel(inv.role)}</span>
                </span>
                <span className="text-xs text-subtle">Expires {formatDate(inv.expires_at)}</span>
                {can("members:manage") && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => revoke.mutate(inv.id)}
                    aria-label={`Cancel invitation for ${inv.email}`}
                  >
                    <X className="size-4" /> Cancel
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <Card className="mt-6">
        <h2 className="mb-3 text-[15px] font-semibold">What each role can do</h2>
        <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
          {(roles.data ?? []).map((r) => (
            <div key={r.value}>
              <dt className="font-medium">{r.label}</dt>
              <dd className="text-muted">{ROLE_HELP[r.value]}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 flex items-center gap-1.5 text-xs text-subtle">
          <ShieldCheck className="size-3" /> Permissions are enforced by the server, not just hidden in the interface.
        </p>
      </Card>

      {inviting && <InviteDialog open onClose={() => setInviting(false)} roles={roles.data ?? []} />}
    </>
  );
}
