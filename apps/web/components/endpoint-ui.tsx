import { Badge } from "@/components/ui";
import type { Endpoint } from "@/lib/types";

export function OnlineBadge({ endpoint }: { endpoint: Pick<Endpoint, "online" | "status" | "source"> }) {
  if (endpoint.status === "revoked") return <Badge tone="neutral">Revoked</Badge>;
  if (endpoint.source === "wazuh") return <Badge tone="info" dot>Via Wazuh</Badge>;
  return endpoint.online ? (
    <Badge tone="success" dot>
      Online
    </Badge>
  ) : (
    <Badge tone="high" dot>
      Offline
    </Badge>
  );
}
