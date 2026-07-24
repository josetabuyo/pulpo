import { getDb } from "../lib/db/client";
import { flows } from "../lib/db/schema";

// Seeds the minimal end-to-end flow for spike validation (plan step 7.1):
// api_trigger(trigger1) -> fetch_http(fetch1). fetch1 hits httpbin so the
// run is verifiable without any other external dependency.
async function main() {
  await getDb()
    .insert(flows)
    .values({
      id: "spike-flow",
      botId: "spike-bot",
      name: "Spike: api_trigger -> fetch_http",
      active: true,
      flowKind: "spike",
      definition: {
        nodes: [
          { id: "trigger1", type: "api_trigger", config: {} },
          {
            id: "fetch1",
            type: "fetch_http",
            config: {
              url: "https://httpbin.org/get?msg={{message}}",
              method: "GET",
              extract: "json",
              output: "context",
            },
          },
        ],
        edges: [{ source: "trigger1", target: "fetch1" }],
      },
    })
    .onConflictDoUpdate({
      target: flows.id,
      set: {
        definition: {
          nodes: [
            { id: "trigger1", type: "api_trigger", config: {} },
            {
              id: "fetch1",
              type: "fetch_http",
              config: {
                url: "https://httpbin.org/get?msg={{message}}",
                method: "GET",
                extract: "json",
                output: "context",
              },
            },
          ],
          edges: [{ source: "trigger1", target: "fetch1" }],
        },
        active: true,
      },
    });

  console.log("Seeded flow 'spike-flow'. Trigger it with:");
  console.log(
    `curl -X POST -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"message":"hello"}' <BASE_URL>/api/flows/spike-flow/trigger/trigger1`
  );
}

main().then(() => process.exit(0));
