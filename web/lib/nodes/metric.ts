import { getDb } from "@/lib/db/client";
import { metrics } from "@/lib/db/schema";
import type { NodeDef } from "./base";
import { interpolate } from "./interpolate";

// TS port of MetricNode (pulpo/graphs/nodes/metric.py). Saving the metric is
// the critical step; the webhook notification is a best-effort side-effect
// (logged on failure, never aborts the flow) -- same contract as the Python
// original.
export const metricNode: NodeDef = {
  label: "Métrica",
  color: "#a16207",
  description: "Registra una métrica de negocio en DB y, opcionalmente, notifica a un sistema externo vía webhook.",
  configSchema: {},
  async run(state, config) {
    const metricName = interpolate((config.metric_name as string) ?? "", state).trim();
    if (!metricName) {
      console.warn("[metric] metric_name vacío — no se registra nada");
      return state;
    }

    const value = interpolate(String(config.value ?? ""), state);
    const rawMetadata = (config.metadata as Record<string, unknown>) ?? {};
    const metadata: Record<string, string> = {};
    if (rawMetadata && typeof rawMetadata === "object") {
      for (const [k, v] of Object.entries(rawMetadata)) {
        metadata[k] = interpolate(String(v), state);
      }
    }

    await getDb().insert(metrics).values({
      botId: state.botId || "",
      contactPhone: state.contactPhone || "",
      contactName: state.contactName || "",
      canal: state.canal || "",
      metricName,
      value,
      metadata: Object.keys(metadata).length ? JSON.stringify(metadata) : null,
    });

    const webhookUrl = ((config.webhook_url as string) ?? "").trim();
    if (webhookUrl) {
      try {
        const res = await fetch(webhookUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            metric_name: metricName,
            value,
            bot_id: state.botId,
            contact_phone: state.contactPhone,
            contact_name: state.contactName,
            canal: state.canal,
            metadata,
          }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      } catch (err) {
        console.error(`[metric] webhook falló url=${webhookUrl} metric=${metricName}`, err);
      }
    }

    return state;
  },
};
