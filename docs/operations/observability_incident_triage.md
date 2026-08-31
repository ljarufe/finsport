# Local Observability And Incident Triage

This stack is local-only and receives the small structured Finsport operational
event stream. PostgreSQL and Django Admin remain the canonical domain audit.

## Start And Sign In

Set a non-empty local password only in the ignored `.env` file:

```dotenv
GRAFANA_ADMIN_PASSWORD=choose-a-local-password
```

Start the normal runtime plus the observability profile:

```bash
make observability-up
```

Open <http://localhost:3000/> and sign in with `GRAFANA_ADMIN_USER` (default
`admin`) and the local password. Anonymous access is disabled. Open
**Finsport > Finsport Operational Incidents**. Pipeline automation remains off
by default; changing `FOOTBALL_PIPELINE_ENABLED` requires recreating/restarting
the affected processes.

Stop only the observability services, preserving their data, with:

```bash
make observability-stop
```

## Find And Inspect An Incident

1. Set the dashboard time range and inspect **Recent actionable incidents**.
2. In Explore, start with
   `{schema="finsport.observability.v1", severity=~"WARNING|ERROR"} | json`.
   Add stable label filters such as `service_name`, `component`, or
   `event_code`. Search a run ID as a parsed JSON field, for example
   `| pipeline_run_id="123"`; IDs and fingerprints are deliberately not Loki
   labels.
3. Expand the log row. Read `human_summary`, `failure_kind`, `provider`,
   `context`, correlation IDs, `exception_message`, and `stacktrace`.
4. `PIPELINE_OVERDUE` means automation was enabled but no completed scheduler
   `SUCCESS`, `DEGRADED`, `FAILED`, or `NO_WORK` activity arrived within the
   900-second cadence plus 900-second grace. Manual runs never suppress it.
5. For `RECONCILIATION_PENDING`, note the source, aggregate counts, oldest age,
   and run IDs. Use Django Admin at <http://localhost:8001/> to filter the
   Competition, Team, or Match source refs by source and `PENDING` status.
6. For any pipeline/capture/experiment ID, use the matching read-only Admin
   record for full domain detail. Do not expect Loki to contain provider
   payloads, SourceRef rows, or complete PipelineRun reports.

Expand the Grafana log details and copy the displayed raw JSON. That JSON is the
core Incident Packet. To review recurrences, query the
`incident_fingerprint`, then derive first seen, last seen, and count from the
selected time range.

## Hand Off To A Ticket Or Debugging Chat

Paste the Incident Packet plus the smallest relevant domain facts. Remove or
redact anything unexpected before sharing it. Never paste credentials, API
keys, tokens, cookies, authorization headers, passwords, DSNs, `.env`, settings
dumps, full request/response bodies, or full provider payloads.

Use this compact template:

```text
Observed at:
Operator impact:
Expected behavior:
Incident Packet JSON:
Related PipelineRun/CaptureRun/experiment IDs:
Relevant Admin finding (no payloads/secrets):
Reproduction or recent runtime change:
```

If the console or runtime clearly fails but Grafana has no event, preserve the
bounded fallback evidence with
`docker compose logs --tail=80 <service>`. Check `alloy`, `loki`, and
`observability-watch` logs, confirm the observability profile is running, and
include the missing-event symptom in the handoff. Do not enable Docker socket
access or copy the entire console history.

## Future Ticket Rule

Every future ticket that introduces a runtime failure mode must report:

```text
Observability / audit impact
new failure modes:
detection:
severity:
diagnostic context:
correlation:
traceback policy:
observability path:
test/UAT evidence:
```

If it introduces none, report `Observability / audit impact: none`.
