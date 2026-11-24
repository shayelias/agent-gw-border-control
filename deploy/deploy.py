"""Create or update one demo agent on Agent Engine.

Usage (from the repo root, after `source config.env`):
    python deploy/deploy.py agent2            # create or update, not bound to the gateway
    python deploy/deploy.py agent1 --bind     # update and bind to the Agent Gateway
Prints the engine ID on the last line.
"""
import os
import sys

# Run from agents/ so the package is shipped as "demo_agents" (the import path the agents use)
AGENTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents"))
os.chdir(AGENTS_DIR)
sys.path.insert(0, AGENTS_DIR)

import vertexai  # noqa: E402
from vertexai._genai import types  # noqa: E402

P, L, N = os.environ["PROJECT_ID"], os.environ["REGION"], os.environ["PROJECT_NUMBER"]
BASE_REQS = ["google-cloud-aiplatform[agent_engines]==2.7.0", "cloudpickle", "pydantic", "requests"]


def engine(env_name):
    eid = os.environ.get(env_name, "")
    return f"projects/{N}/locations/{L}/reasoningEngines/{eid}" if eid else ""


def spec(name):
    common = {"PROJECT_ID": P, "REGION": L}
    if name == "agent1":
        from demo_agents.agent1 import Agent1
        return Agent1(), BASE_REQS, {**common, "AGENT2_RESOURCE": engine("AGENT2_ID"),
                                     "AGENT3_RESOURCE": engine("AGENT3_ID"),
                                     "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "False"}
    if name == "agent2":
        from demo_agents.agent2 import Agent2
        return Agent2(), BASE_REQS + ["cloud-sql-python-connector[pymysql]", "google-cloud-secret-manager"], {
            **common, "SQL_CONNECTION_NAME": f"{P}:{L}:{os.environ['SQL_INSTANCE']}",
            "DB_NAME": os.environ["DB_NAME"], "DB_USER": os.environ["DB_USER"],
            "DB_SECRET": f"projects/{P}/secrets/{os.environ['DB_SECRET']}/versions/latest",
            "ASSERTION_ISSUER": f"{os.environ['WEB_SA_NAME']}@{P}.iam.gserviceaccount.com",
            "REQUIRE_ASSERTION": os.environ.get("REQUIRE_ASSERTION", "true"),
            "GOOGLE_API_PREVENT_AGENT_TOKEN_SHARING_FOR_GCP_SERVICES": "False"}
    if name == "agent3":
        from demo_agents.agent3 import Agent3
        return Agent3(), BASE_REQS + ["google-genai"], {**common, "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true"}
    sys.exit(f"unknown agent {name}")


def main():
    name, bind = sys.argv[1], "--bind" in sys.argv
    agent, reqs, env = spec(name)
    gateway = None
    if bind:
        gateway = types.ReasoningEngineSpecDeploymentSpecAgentGatewayConfig(
            agent_to_anywhere_config=types.ReasoningEngineSpecDeploymentSpecAgentGatewayConfigAgentToAnywhereConfig(
                agent_gateway=f"projects/{P}/locations/{L}/agentGateways/{os.environ['GATEWAY']}"))
    config = types.AgentEngineConfig(
        display_name=f"demo-{name}", gcs_dir_name=f"demo-{name}",
        identity_type=types.IdentityType.AGENT_IDENTITY,  # each agent gets its own principal, no keys
        staging_bucket=os.environ["STAGING_BUCKET"], requirements=reqs,
        extra_packages=["demo_agents"],
        env_vars=env, agent_gateway_config=gateway, labels={"demo": "agent-gateway"})
    client = vertexai.Client(project=P, location=L)
    existing = engine(name.upper() + "_ID")
    remote = (client.agent_engines.update(name=existing, agent=agent, config=config) if existing
              else client.agent_engines.create(agent=agent, config=config))
    print(remote.api_resource.name.rsplit("/", 1)[-1])


if __name__ == "__main__":
    main()
