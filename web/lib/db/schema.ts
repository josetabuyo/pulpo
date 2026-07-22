import {
  pgTable,
  text,
  boolean,
  timestamp,
  jsonb,
  serial,
} from "drizzle-orm/pg-core";

// Mirrors pulpo/core/db.py (SQLite, raw SQL) -- that file is the source of
// truth for this schema, not any Python model (there isn't one).

export const flows = pgTable("flows", {
  id: text("id").primaryKey(),
  botId: text("bot_id").notNull(),
  name: text("name").notNull(),
  definition: jsonb("definition").notNull(),
  connectionId: text("connection_id"),
  contactPhone: text("contact_phone"),
  active: boolean("active").notNull().default(true),
  contactFilter: jsonb("contact_filter"),
  flowKind: text("flow_kind"),
  createdAt: timestamp("created_at", { withTimezone: true }).defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow(),
});

export const flowRuns = pgTable("flow_runs", {
  runId: text("run_id").primaryKey(),
  flowId: text("flow_id").notNull(),
  botId: text("bot_id").notNull(),
  connectionId: text("connection_id"),
  startedAt: timestamp("started_at", { withTimezone: true }).defaultNow(),
  endedAt: timestamp("ended_at", { withTimezone: true }),
  // running | completed | waiting_gate | error | expired | handed_off
  status: text("status").notNull().default("running"),
  triggerData: jsonb("trigger_data"),
  contactPhone: text("contact_phone"),
  resumeNodeId: text("resume_node_id"),
  slotsJson: jsonb("slots_json"),
  isSim: boolean("is_sim").notNull().default(false),
  // not present in the Python schema -- lets us correlate a flow_run with
  // the Workflow DevKit run that executed it, for `npx workflow inspect run`.
  workflowRunId: text("workflow_run_id"),
});

export const flowRunSteps = pgTable("flow_run_steps", {
  id: serial("id").primaryKey(),
  runId: text("run_id")
    .notNull()
    .references(() => flowRuns.runId),
  nodeId: text("node_id").notNull(),
  nodeType: text("node_type").notNull(),
  startedAt: timestamp("started_at", { withTimezone: true }).defaultNow(),
  endedAt: timestamp("ended_at", { withTimezone: true }),
  inputState: jsonb("input_state"),
  outputState: jsonb("output_state"),
  branchTaken: text("branch_taken"),
  // ok | blocked | error
  status: text("status").notNull().default("ok"),
});
