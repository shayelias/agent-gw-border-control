# Border Control for AI Agents

A working demo of **Google Cloud Agent Gateway**: three agents on Agent Engine, one gateway that decides where their traffic may go, and a signed user assertion that proves on whose behalf they act.

Companion code for the article *Border Control for AI Agents: Governing Agent Traffic with Google Cloud Agent Gateway* **[ARTICLE LINK]**.

> **Preview.** Agent Gateway and Agent Registry are pre-GA at the time of writing. The scripts use `gcloud alpha`/`beta` commands and `v1alpha`/`v1beta1` APIs, which may change.

## What it shows

| # | Scenario | What happens |
|---|---|---|
| 1 | Identity hand-off | The web app verifies the IAP user and signs a 60-second user assertion. Agent 1 carries it to Agent 2, which verifies it and queries the database as that user. A **Tamper** button changes the user after signing, and Agent 2 rejects it. |
| 2 | Which agent may Agent 1 call? | A gateway policy allows Agent 1 → Agent 2 and denies Agent 1 → Agent 3 (`403`), even though IAM alone would allow both. |
| 3 | Search without internet | Agent 3's only tool is Google Search (`types.Tool(google_search=types.GoogleSearch())`). Its only outbound call is to the Gemini API, through the gateway. |
| 4 | A website is blocked | Agent 3 tries a plain HTTP request to a public website. Nothing allows it, so the gateway returns `403 Egress request is not authorized.` |

> **[docs/architecture.png]**

```
User ─► IAP ─► web app (Cloud Run) ─┬─► Agent 1 ─┐                 ┌─► Agent 2 ─► Cloud SQL
                                    │            ├─► Agent Gateway ┼─► Gemini API (Google runs the search)
                                    └─► Agent 3 ─┘   (IAP policy)  └─✕ public websites
                                                     A1 → A3 ✕
```

## How it works

- **Agent identity.** Each agent is deployed with `AGENT_IDENTITY` and gets its own principal, with no service-account keys:
  `principal://agents.global.org-ORG_ID.system.id.goog/resources/aiplatform/projects/PROJECT_NUMBER/locations/REGION/reasoningEngines/ENGINE_ID`
- **Gateway binding.** Agents 1 and 3 are bound to the gateway with a deployment setting (`agentGatewayConfig`). The runtime sends all their outbound traffic there; the agent code has no proxy settings.
- **Decisions.** For each request, the gateway asks its IAP authorization extension. IAP authenticates the agent, matches the destination against Agent Registry, and evaluates the IAM access policies bound to the gateway. A rule applies only when its condition matches, DENY beats ALLOW, and in enforce mode anything no rule allows is denied.
- **On whose behalf.** The gateway does not inspect end-user tokens. The web app verifies IAP's signed JWT, then asks Google (IAM Credentials `signJwt`) to sign a short assertion as its service account: `iss`, `sub` (the user), `aud` (Agent 2), `exp` (60 s), `jti` (single use). Agent 2 verifies it with the public keys Google publishes for that service account, and takes the user only from the token.

## Layout

```
agents/demo_agents/   agent1.py (orchestrator), agent2.py (database), agent3.py (search), common.py
deploy/deploy.py      create or update one agent; --bind attaches it to the gateway
web/                  the demo page (Flask on Cloud Run)
gateway/              gateway, IAP authz extension and authz policy templates
policies/             egress access policy templates
sql/init_db.py        table and seed rows
scripts/              numbered setup steps, enforce, teardown
config.env.example    every name and ID the scripts use
```

Templates use `${VAR}` placeholders filled from `config.env` by `scripts/render.py`. No project, organization or account values are committed.

## Prerequisites

- A Google Cloud **organization** (agent identities live in the organization's agent identity pool) and a project where you can create gateways, IAM policies and Cloud SQL.
- Access to Agent Gateway and Agent Registry (preview).
- `gcloud` with the `alpha` and `beta` components, Python 3.12, and `openssl`.
- A region where Agent Gateway is available. The demo ran in `me-west1`; Agent 3 calls Gemini on the `global` endpoint.

## Setup

```bash
cp config.env.example config.env     # fill in PROJECT_ID, PROJECT_NUMBER, ORG_ID, REGION, IAP_MEMBER, DEMO_USER_EMAIL
./scripts/00-setup.sh                # APIs, staging bucket, local venv
./scripts/10-gateway.sh              # gateway + IAP authz extension (DRY_RUN) + authz policy
./scripts/20-database.sh             # Cloud SQL, DB user, password in Secret Manager, table
./scripts/30-agents.sh               # create the three agents, grant each identity its roles
./scripts/40-registry.sh             # register Google API hosts, Agent 2 and Agent 3
./scripts/50-policies.sh             # egress policies, bound to the gateway
./scripts/60-bind.sh                 # bind Agent 1 and Agent 3 to the gateway
./scripts/70-web.sh                  # web app on Cloud Run behind IAP; prints the URL
```

Each script writes the IDs it creates (engine IDs, registry endpoint IDs) back into `config.env`.

### Dry-run, then enforce

The gateway starts in `DRY_RUN`: decisions are logged, nothing is blocked. Use the demo for a while, then look for requests that **would** be denied:

```
protoPayload.serviceName="iap.googleapis.com"
protoPayload.authorizationInfo.granted=false
protoPayload.metadata.dryRun=true
```

Add an ALLOW for anything legitimate you find (`policies/platform-startup.json.tmpl` exists because the agent runtime makes a startup `GetProject` call that would otherwise be denied). Then:

```bash
./scripts/80-enforce.sh
```

Enforce mode applies to the whole gateway, and policy changes can take a few minutes to apply.

## Walkthrough

Open the URL printed by `70-web.sh` and sign in as `IAP_MEMBER`.

1. **Scenario 1.** *query db with A2* returns your rows. The **JWT debug** box shows IAP's JWT (decoded, signature shortened), the signed assertion (raw and decoded), and Agent 2's checks. *Tamper* changes the user inside the assertion: Agent 2 reports the signature check failed, and no query runs.
2. **Scenario 2.** *A1 → A2* is allowed. *A1 → A3* is denied by the gateway policy (`403`), and Agent 3 is never reached. Each result links to its log queries.
3. **Scenario 3.** Ask a question. The page shows the answer, the searches Google ran, and the tool definition.
4. **Scenario 4.** *Open website* with any public site: `403 Egress request is not authorized.`

Useful queries:

```
# every gateway decision, with the agent and the destination
protoPayload.serviceName="iap.googleapis.com"
protoPayload.metadata.dryRun=false

# the gateway's request log
resource.type="networkservices.googleapis.com/Gateway"
resource.labels.gateway_name="GATEWAY"
```

```bash
gcloud iam access-policies describe a1-to-agents --location=global --project=PROJECT_ID
gcloud iam policy-bindings list --location=global --project=PROJECT_ID
```

## Known limitations and production notes

- **Fail closed.** This repo sets `failOpen: false` on the IAP extension. The original demo ran with `true`, where the gateway **allows** requests if IAP does not answer.
- **Logging gap.** Denied agent-to-agent calls appeared in the IAP audit log but not in the gateway request log; denied website calls appeared in both. Alert on the IAP audit log.
- **IAM is broad.** The agents hold project-wide `aiplatform.user`, so IAM alone would let any agent call any other. Narrow it per agent so IAM and the gateway back each other up.
- **Not everything goes through the gateway.** The web app's calls to the agents and Agent 2's database connection are direct, and Agent 2 is not bound to the gateway.
- **Single-use check per instance.** Agent 2 remembers used `jti` values in memory, so the check covers one instance; the 60-second expiry bounds replay across instances.
- **Database privileges.** Revoke `cloudsqlsuperuser` from the Agent 2 database user (Cloud SQL grants it to users created through the API).
- **Private network path.** "Through the gateway to a Google API" is not the same as "on Google's private network end to end", which needs Private Service Connect and private DNS.
- **Shared package.** All agents ship the whole `demo_agents` package; in production, package each agent separately.

## Status of this code

The agents, the web app and the policy definitions are the code that ran in the demo, with project-specific values moved to configuration. The setup scripts reproduce the commands used to build the demo, but have **not** been run end to end as a single sequence in a fresh project. Expect to adjust them, especially while the services are in preview.

## Cost and teardown

Cloud SQL, the three Agent Engine deployments and Cloud Run bill while they exist.

```bash
./scripts/99-teardown.sh
```

## License

No license is granted at this time. You are welcome to read the code; please ask before reusing it.
