"""Agent 1: the orchestrator. Calls Agent 2 (and tries Agent 3) through the Agent Gateway."""
import os

from demo_agents.common import PROJECT, code_ref

LOCATION = os.environ["REGION"]


class Agent1:
    def set_up(self):
        import vertexai

        self._client = vertexai.Client(project=PROJECT, location=LOCATION)
        self._agent2_name = os.environ["AGENT2_RESOURCE"]
        self._agent2 = None

    def register_operations(self):
        return {"": ["move_cookie", "query_db", "call_agent"]}

    def _remote_agent2(self):
        if self._agent2 is None:
            self._agent2 = self._client.agent_engines.get(name=self._agent2_name)
        return self._agent2

    def _traced_call(self, method: str, _remote=None, **kwargs):
        """Call an agent method and capture the exact HTTP request the SDK sends."""
        remote = _remote or self._remote_agent2()
        sent = {}
        api = None
        orig = None
        try:
            api = remote.api_client._api_client
            orig = api.request

            def spy(http_method, path, request_dict, *a, **k):
                sent.update({"http_method": str(http_method).upper(), "path": path,
                             "json_body": request_dict})
                return orig(http_method, path, request_dict, *a, **k)

            api.request = spy
        except Exception as exc:  # debug capture must never break the call
            sent["capture_error"] = f"{type(exc).__name__}: {exc}"
        try:
            result = getattr(remote, method)(**kwargs)
        finally:
            if api is not None and orig is not None:
                api.request = orig
        proxy_env = {k: v for k, v in os.environ.items()
                     if "PROXY" in k.upper() or k in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE")}
        return result, {"sdk_request": sent, "runtime_proxy_env": proxy_env}

    def call_agent(self, target: str, email: str, assertion: str = "") -> dict:
        """S4: call another agent (A2 or A3) through the gateway; the gateway policy decides."""
        targets = {
            "A2": (os.environ["AGENT2_RESOURCE"], "query_db", {"email": email, "assertion": assertion}),
            "A3": (os.environ["AGENT3_RESOURCE"], "describe_tools", {}),
        }
        name, method, kwargs = targets[target]
        flow = [{"n": 3, "title": "web app -> Agent 1", "arrow": "Agent Engine API call",
                 "sub": f"Agent 1 is asked to call {target}", "data": {"user": email, "target": target},
                 "code": code_ref()}]
        try:
            remote = self._client.agent_engines.get(name=name)
            result, debug = self._traced_call(method, _remote=remote, **kwargs)
        except Exception as exc:
            flow.append({"n": 4, "title": f"Agent 1 -> the gateway -> {target}",
                         "arrow": "Agent Engine API call through the gateway",
                         "sub": "The gateway answered; the call did not go through",
                         "data": {"error": f"{type(exc).__name__}: {str(exc)[:240]}"},
                         "verdict": "DENIED", "code": code_ref()})
            return {"verdict": "DENIED", "target": target, "flow": flow, "trace": []}
        flow.append({"n": 4, "title": f"Agent 1 -> the gateway -> {target}",
                     "arrow": "Agent Engine API call through the gateway",
                     "sub": f"{target} answered", "data": {"agent": result.get("agent", target)},
                     "verdict": "ALLOW", "debug": debug, "code": code_ref()})
        return {"verdict": "ALLOW", "target": target, "flow": flow, "trace": [],
                "identity_check": result.get("identity_check")}

    def move_cookie(self, cookie: str, email: str, assertion: str = "") -> dict:
        """S1b: pass the user and cookie to Agent2 through the gateway."""
        trace = [{"step": "Agent 1 read the cookie from the request header",
                  "code": code_ref()}]
        flow = [{"n": 3, "title": "web app -> Agent 1", "arrow": "Agent Engine API call",
                 "sub": "Agent 1 received the identity from the web app",
                 "data": {"user": email, "cookie": cookie}, "code": code_ref()}]
        # the assertion is passed through unchanged: Agent 1 cannot edit it without breaking the signature
        result, debug = self._traced_call("enroll_cookie", cookie=cookie, email=email, assertion=assertion)
        trace.append({"step": "Agent 1 -> the gateway -> Agent 2 (cookie delivered)", "code": code_ref()})
        trace.append({"step": "Agent 2 stored the cookie", **result})
        flow.append({"n": 4, "title": "Agent 1 -> the gateway -> Agent 2",
                     "arrow": "Agent Engine API call through the gateway",
                     "sub": "This is what Agent 2 reports it received",
                     "data": result["received"], "debug": debug, "code": code_ref()})
        flow.append({"n": 5, "title": "Agent 2 -> Cloud SQL",
                     "arrow": "database connection",
                     "sub": "Agent 2 stored the row",
                     "data": {"user": result["received"]["user"],
                              "cookie": result["received"].get("cookie", "(not stored)")},
                     "code": result["code"]})
        return {"verdict": "REJECTED" if result.get("rejected") else "ALLOW", "flow": flow, "trace": trace,
                "identity_check": result.get("identity_check")}

    def query_db(self, cookie: str, email: str, assertion: str = "") -> dict:
        """S1c: ask Agent2 (via the gateway) for the rows that belong to the user."""
        trace = []
        flow = [{"n": 3, "title": "web app -> Agent 1", "arrow": "Agent Engine API call",
                 "sub": "Agent 1 received the user from the web app",
                 "data": {"user": email}, "code": code_ref()}]
        result, debug = self._traced_call("query_db", email=email, assertion=assertion)
        trace.append({"step": "Agent 2 ran the DB query", "code": result["code"]})
        flow.append({"n": 4, "title": "Agent 1 -> the gateway -> Agent 2",
                     "arrow": "Agent Engine API call through the gateway",
                     "sub": "This is what Agent 2 reports it received",
                     "data": result["received"], "debug": debug, "code": code_ref()})
        flow.append({"n": 5, "title": "Agent 2 -> Cloud SQL",
                     "arrow": "database query",
                     "sub": "The user is used in the WHERE clause",
                     "data": {"user": result["received"]["user"], "rows returned": str(len(result["rows"]))},
                     "code": result["code"]})
        return {"verdict": "REJECTED" if result.get("rejected") else "ALLOW", "flow": flow,
                "sql": result["sql"], "rows": result["rows"], "trace": trace,
                "identity_check": result.get("identity_check")}
