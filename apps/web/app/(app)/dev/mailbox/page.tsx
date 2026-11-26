"use client";

import { useQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";
import { Button, Callout, Card, EmptyState, PageHeader } from "@/components/ui";
import { timeAgo } from "@/lib/format";

type Mail = { to: string; subject: string; body: string; sent_at: string };

function linkify(text: string) {
  return text.split(/(https?:\/\/\S+)/g).map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <a key={i} href={part} className="break-all text-primary-text underline">
        {part}
      </a>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export default function DevMailboxPage() {
  const { data, refetch, isFetching } = useQuery({
    queryKey: ["dev-mailbox"],
    queryFn: async () => {
      const res = await fetch("/api/v1/dev/mailbox");
      return res.ok ? ((await res.json()) as Mail[]) : [];
    },
  });

  return (
    <>
      <PageHeader
        title="Developer mailbox"
        description="Development only. Emails the platform would have sent (invitations, password resets) appear here."
        actions={
          <Button variant="secondary" loading={isFetching} onClick={() => refetch()}>
            Refresh
          </Button>
        }
      />
      <div className="mb-4">
        <Callout tone="warning">This page and its API are disabled outside development.</Callout>
      </div>
      {!data?.length ? (
        <Card>
          <EmptyState icon={<Inbox className="size-5" />} title="No emails yet" />
        </Card>
      ) : (
        <div className="space-y-3">
          {data.map((m, i) => (
            <Card key={i}>
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <p className="font-medium">{m.subject}</p>
                <span className="text-xs text-subtle">{timeAgo(m.sent_at)}</span>
              </div>
              <p className="text-sm text-muted">To: {m.to}</p>
              <p className="mt-3 text-sm whitespace-pre-wrap">{linkify(m.body)}</p>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
