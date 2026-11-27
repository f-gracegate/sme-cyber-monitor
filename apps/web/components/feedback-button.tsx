"use client";

import { useMutation } from "@tanstack/react-query";
import { MessageSquarePlus } from "lucide-react";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Dialog } from "@/components/dialog";
import { useToast } from "@/components/providers";
import { Button, Callout, Field, Select, Textarea } from "@/components/ui";
import { api, errorMessage } from "@/lib/api";

/** Pilot feedback: anyone can tell the product team what's confusing, broken or missing. */
export function FeedbackButton() {
  const pathname = usePathname();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState("idea");
  const [message, setMessage] = useState("");
  const [rating, setRating] = useState<number | null>(null);
  const send = useMutation({
    mutationFn: () =>
      api<{ message: string }>("/feedback", {
        method: "POST",
        body: { kind, message: message.trim(), page: pathname, rating: rating ?? undefined },
      }),
    onSuccess: (r) => {
      toast("success", r.message);
      setOpen(false);
      setMessage("");
      setRating(null);
    },
  });
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="inline-flex size-9 items-center justify-center rounded-lg text-muted hover:bg-surface-2 hover:text-fg"
        aria-label="Send feedback"
        title="Send feedback"
      >
        <MessageSquarePlus className="size-[18px]" />
      </button>
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        title="Tell us what you think"
        description="Something confusing, broken or missing? We read every message during the pilot."
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button loading={send.isPending} disabled={message.trim().length < 3} onClick={() => send.mutate()}>
              Send
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {send.isError && <Callout tone="critical">{errorMessage(send.error)}</Callout>}
          <Field label="About" htmlFor="fb-kind">
            <Select id="fb-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="idea">An idea or request</option>
              <option value="problem">Something isn&apos;t working</option>
              <option value="question">A question</option>
              <option value="praise">Something I like</option>
            </Select>
          </Field>
          <Field label="Message" htmlFor="fb-message">
            <Textarea id="fb-message" rows={4} value={message} onChange={(e) => setMessage(e.target.value)} maxLength={5000} />
          </Field>
          <fieldset>
            <legend className="mb-1.5 text-sm font-medium text-fg">How useful is the product so far? (optional)</legend>
            <div className="flex gap-1.5">
              {[1, 2, 3, 4, 5].map((n) => (
                <button
                  key={n}
                  type="button"
                  aria-pressed={rating === n}
                  onClick={() => setRating(rating === n ? null : n)}
                  className={`size-9 rounded-lg border text-sm font-medium ${rating === n ? "border-primary bg-primary text-white" : "border-border hover:bg-surface-2"}`}
                >
                  {n}
                </button>
              ))}
            </div>
          </fieldset>
        </div>
      </Dialog>
    </>
  );
}
