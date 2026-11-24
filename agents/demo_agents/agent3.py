"""Agent 3: answers questions with Gemini grounded by Google Search.

The search tool is configured in tools() below. The agent never opens a website:
its only outbound call is to the Gemini API, and Google runs the search.
open_website() is a demo method (not a Gemini tool): it tries a plain HTTP request
to a public site, which the gateway refuses.
"""
import os
import re

from demo_agents.common import PROJECT, code_ref

MODEL = os.environ.get("MODEL", "gemini-2.5-flash")
ENDPOINT_LOCATION = os.environ.get("MODEL_LOCATION", "global")


class Agent3:
    def set_up(self):
        self._client = None

    def register_operations(self):
        return {"": ["ask", "describe_tools", "open_website"]}

    def _genai(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(vertexai=True, project=PROJECT,
                                        location=ENDPOINT_LOCATION)
        return self._client

    def tools(self):
        """The agent's tool list, and the code line that defines each tool."""
        from google.genai import types

        search = types.Tool(google_search=types.GoogleSearch())  # the agent's only tool
        ref = code_ref()
        return [search], [{
            "name": "google_search",
            "description": "Gemini grounding with Google Search: Google runs the search on its side",
            "code": {"where": ref["where"].rsplit(":", 1)[0] + ":" + str(int(ref["where"].rsplit(":", 1)[1]) - 1),
                     "code": "search = types.Tool(google_search=types.GoogleSearch())"},
        }]

    def describe_tools(self) -> dict:
        _, listing = self.tools()
        return {"agent": "Agent 3", "model": MODEL, "model_endpoint": ENDPOINT_LOCATION,
                "tools": listing}

    def ask(self, question: str) -> dict:
        from google.genai import types

        tool_objs, listing = self.tools()
        response = self._genai().models.generate_content(
            model=MODEL, contents=question,
            config=types.GenerateContentConfig(tools=tool_objs))
        meta = response.candidates[0].grounding_metadata if response.candidates else None
        sources = []
        for chunk in (meta.grounding_chunks or []) if meta else []:
            if chunk.web:
                sources.append({"title": chunk.web.title, "uri": chunk.web.uri})
        return {"agent": "Agent 3", "answer": response.text, "sources": sources,
                "search_queries": list(meta.web_search_queries or []) if meta else [],
                "model": MODEL, "model_endpoint": ENDPOINT_LOCATION,
                "tools": listing, "code": code_ref()}

    def open_website(self, url: str) -> dict:
        """Scenario 4: try to open a public website directly; the gateway decides."""
        import requests

        if not re.match(r"^https?://", url):
            url = "https://" + url
        proxy_env = {k: v for k, v in os.environ.items() if "PROXY" in k.upper()}
        try:
            resp = requests.get(url, timeout=10, allow_redirects=False,
                                headers={"User-Agent": "Agent3-demo"})
        except Exception as exc:
            return {"agent": "Agent 3", "url": url, "verdict": "DENIED",
                    "error": f"{type(exc).__name__}: {str(exc)[:300]}",
                    "runtime_proxy_env": proxy_env, "code": code_ref()}
        denied = resp.status_code == 403 and "Egress request is not authorized" in resp.text
        return {"agent": "Agent 3", "url": url, "verdict": "DENIED" if denied else "ALLOW",
                "status": resp.status_code, "excerpt": resp.text[:300],
                "runtime_proxy_env": proxy_env, "code": code_ref()}
