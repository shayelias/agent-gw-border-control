"""Demo web app behind IAP: 1 identity hand-off, 2 agent-to-agent policy, 3 search, 4 website try."""
import base64
import html
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import vertexai
from flask import Flask, jsonify, request

PROJECT = os.environ["PROJECT_ID"]
LOCATION = os.environ["REGION"]
AGENT1 = os.environ["AGENT1_RESOURCE"]
AGENT2 = os.environ["AGENT2_RESOURCE"]
AGENT3 = os.environ["AGENT3_RESOURCE"]
GATEWAY = os.environ["GATEWAY"]
A1_POLICY = os.environ.get("A1_POLICY", "a1-to-agents")
AGENT2_ENDPOINT = os.environ["AGENT2_ENDPOINT"]  # Agent Registry endpoint IDs (agentregistry-...)
AGENT3_ENDPOINT = os.environ["AGENT3_ENDPOINT"]

IAP_AUDIENCE = os.environ["IAP_AUDIENCE"]  # /projects/PROJECT_NUMBER/locations/REGION/services/SERVICE
IAP_CERTS = "https://www.gstatic.com/iap/verify/public_key"
WEB_SA = os.environ["WEB_SA"]  # this service's service account email
ASSERTION_AUDIENCE = os.environ.get("ASSERTION_AUDIENCE", "agent2")
ASSERTION_TTL = 60

app = Flask(__name__)
_engines = {}
_session = None


def engine(name):
    if name not in _engines:
        client = vertexai.Client(project=PROJECT, location=LOCATION)
        _engines[name] = client.agent_engines.get(name=name)
    return _engines[name]


def agent1():
    return engine(AGENT1)


def identity():
    raw = request.headers.get("X-Goog-Authenticated-User-Email", "")
    email = raw.split(":", 1)[-1] if raw else ""
    return email, request.headers.get("Cookie", "")


def _b64json(seg):
    return json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))


def _decode_unverified(token):
    head, payload, _ = token.split(".")
    return _b64json(head), _b64json(payload)


def verify_iap():
    """Verify IAP's signed header (ES256, Google's IAP keys); return (claims, debug)."""
    from google.auth.transport import requests as ga_requests
    from google.oauth2 import id_token

    token = request.headers.get("X-Goog-IAP-JWT-Assertion", "")
    if not token:
        raise PermissionError("no X-Goog-IAP-JWT-Assertion header")
    try:
        claims = id_token.verify_token(token, ga_requests.Request(), audience=IAP_AUDIENCE, certs_url=IAP_CERTS)
    except Exception as exc:
        try:
            aud = _decode_unverified(token)[1].get("aud")
        except Exception:
            aud = "?"
        raise PermissionError(f"IAP JWT not verified ({exc}); expected aud {IAP_AUDIENCE}, token aud {aud}")
    if claims.get("iss") != "https://cloud.google.com/iap":
        raise PermissionError(f"unexpected IAP JWT issuer {claims.get('iss')}")
    debug = {"header": _decode_unverified(token)[0], "claims": claims,
             "signature": "…" + token.rsplit(".", 1)[-1][-6:], "audience_checked": IAP_AUDIENCE}
    return claims, debug


def sign_assertion(user):
    """Sign a short user assertion for Agent 2 as WEB_SA (IAM Credentials signJwt; no key file)."""
    global _session
    if _session is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        _session = AuthorizedSession(creds)
    now = int(time.time())
    claims = {"iss": WEB_SA, "sub": user, "aud": ASSERTION_AUDIENCE,
              "iat": now, "exp": now + ASSERTION_TTL, "jti": uuid.uuid4().hex}
    resp = _session.post(f"https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{WEB_SA}:signJwt",
                         json={"payload": json.dumps(claims)}, timeout=10)
    resp.raise_for_status()
    body = resp.json()
    return body["signedJwt"], body["keyId"]


def _tampered(token):
    """Demo only: change the user inside a signed assertion, keeping the old signature."""
    head, payload, sig = token.split(".")
    claims = _b64json(payload)
    claims["sub"] = "someone-else@example.com"
    forged = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return f"{head}.{forged}.{sig}"


def user_assertion(tamper=False):
    """Verify the IAP user, then sign the assertion Agent 1 passes to Agent 2."""
    claims, iap_debug = verify_iap()
    user = claims["email"]
    token, key_id = sign_assertion(user)
    sent = _tampered(token) if tamper else token
    head, payload = _decode_unverified(sent)
    return user, sent, {"iap_jwt": iap_debug,
                        "assertion": {"raw": sent, "header": head, "claims": payload,
                                      "signed_by": WEB_SA, "key_id": key_id, "tampered": tamper}}


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Gateway demo</title>
<style>
 body{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 16px;color:#1f2937}
 h1{font-size:1.4rem} h2{font-size:1.1rem;margin-top:2rem}
 code,pre{background:#f3f4f6;padding:2px 6px;border-radius:4px;font-size:.85rem}
 pre{padding:10px;overflow:auto;white-space:pre-wrap;word-break:break-all}
 button{padding:8px 16px;margin:4px 8px 4px 0;cursor:pointer}
 input{padding:8px;width:min(420px,70%)}
 .ALLOW{color:#047857;font-weight:700} .BLOCK,.DENIED,.REJECTED{color:#b91c1c;font-weight:700}
 .jwt{margin-top:12px;border-color:#6b4fd8} .jwt h4{margin:14px 0 4px;font-size:.92rem}
 .checks{list-style:none;padding-left:0;margin:4px 0} .checks .ok{color:#047857} .checks .bad{color:#b91c1c;font-weight:700}
 pre.raw{word-break:break-all;font-size:.75rem}
 .logs a{display:inline-block;margin:4px 0}
 .step{border-left:3px solid #9ca3af;padding:2px 10px;margin:8px 0}
 .card{border:1px solid #d1d5db;border-radius:10px;padding:10px 14px;margin:0;background:#fff}
 .card h3{margin:0 0 2px;font-size:1rem} .card .sub{color:#6b7280;font-size:.85rem;margin-bottom:6px}
 .num{display:inline-block;width:24px;height:24px;line-height:24px;text-align:center;border-radius:50%;background:#1f6feb;color:#fff;font-size:.8rem;margin-right:8px}
 .chip{display:inline-block;background:#f3f4f6;border:1px solid #d1d5db;border-radius:6px;padding:2px 8px;margin:2px 6px 2px 0;font-size:.82rem;word-break:break-all}
 .chip.user{background:#fff4d6;border-color:#d97706;font-weight:700}
 .arrow{text-align:center;color:#0b8a7a;font-weight:600;font-size:.85rem;margin:2px 0}
 details{margin-top:12px} summary{cursor:pointer;color:#4b5563}
</style></head><body>
<h1>hello __NAME__ iap ok!</h1>
<p>your cookie is <code id="cookie">__COOKIE__</code></p>

<h2>1 - identity hand-off: A1 -&gt; A2 -&gt; DB</h2>
<button onclick="run('/api/move-cookie','s1')">Agent Orchestrator: A1->A2</button>
<button onclick="run('/api/query-db','s1')">query db with A2</button>
<button onclick="run('/api/query-db','s1',{tamper:true})">Tamper: change the user inside the assertion</button>
<div id="s1"></div>

<h2>2 - which agent may Agent 1 call?</h2>
<p>The gateway policy <code>__A1_POLICY__</code> says: A1 may call A2, A1 may NOT call A3.</p>
<button onclick="run('/api/call-agent','s4',{target:'A2'})">A1 -&gt; A2</button>
<button onclick="run('/api/call-agent','s4',{target:'A3'})">A1 -&gt; A3</button>
<div id="s4"></div>

<h2>3 - search without internet (Agent 3)</h2>
<p>Agent 3's only tool is Google Search: <code>search = types.Tool(google_search=types.GoogleSearch())</code>. Its only outbound call is to the Gemini API, through the gateway. Google runs the search.</p>
<input id="q3" value="Will Beitar Jerusalem win Maccabi Haifa in the next match in Tedi?" aria-label="question">
<button onclick="runTo('/api/ask','s3',{question:document.getElementById('q3').value})">Ask</button>
<div id="s3"></div>

<h2>4 - Agent 3 tries to open a website</h2>
<p>The same agent sends a plain HTTP request to a public site. The gateway policy allows Agent 3 to reach Google APIs only.</p>
<input id="u4" value="www.wikipedia.org" aria-label="website">
<button onclick="runTo('/api/open-website','s4b',{url:document.getElementById('u4').value})">Open website</button>
<div id="s4b"></div>

<script>
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
function chip(k,v){const u=(k==='user'); return '<span class="chip'+(u?' user':'')+'"><b>'+esc(k)+':</b> '+esc(v)+'</span>';}
function card(n,title,sub,data,verdict,code,debug){
  let h='<div class="card"><h3><span class="num">'+n+'</span>'+esc(title)+(verdict?' &rarr; <span class="'+esc(verdict)+'">'+esc(verdict)+'</span>':'')+'</h3><div class="sub">'+esc(sub)+'</div>';
  Object.entries(data||{}).forEach(([k,v]) => { h+=chip(k,v); });
  if(code && code.where) h+='<div class="sub" style="margin-top:6px">code: <code>'+esc(code.where)+'</code> <code>'+esc(code.code||'')+'</code></div>';
  if(debug) h+='<details><summary>debug: the raw request Agent 1 sent</summary><pre>'+esc(JSON.stringify(debug,null,2))+'</pre></details>';
  return h+'</div>';
}
function arrow(t){return '<div class="arrow">&darr; '+esc(t)+'</div>';}
function renderFlow(d){
  const hdr=d.web_header||'', ck=document.getElementById('cookie').textContent;
  const user=hdr.split(':').slice(-1)[0];
  let h='<p>verdict: <span class="'+esc(d.verdict)+'">'+esc(d.verdict)+'</span></p>';
  h+=card(1,'Browser -> IAP','IAP signs you in with your Google account',{user:user});
  h+=arrow('IAP adds request headers');
  h+=card(2,'IAP -> web app (Cloud Run)','The web app verifies the IAP signed JWT, then signs a 60 s user assertion for Agent 2',{'header X-Goog-Authenticated-User-Email':hdr,user:user,cookie:ck});
  (d.flow||[]).forEach(f => { h+=arrow(f.arrow)+card(f.n,f.title,f.sub,f.data,f.verdict,f.code,f.debug); });
  if(d.sql) h+='<p>query:</p><pre>'+esc(d.sql)+'</pre><p>rows:</p><pre>'+esc(JSON.stringify(d.rows,null,2))+'</pre>';
  if(d.policy_note){ const n=d.policy_note;
    h+='<div class="card jwt"><h3>Decided by the gateway policy &rarr; <span class="DENIED">'+esc(n.effect)+'</span></h3>'+
       '<div class="sub">'+esc(n.text)+'</div>'+chip('policy',n.policy)+chip('rule',n.rule)+chip('bound to',n.bound_to)+'</div>'; }
  h+=jwtPanels(d);
  h+='<details><summary>All code lines</summary>';
  (d.trace||[]).forEach(t => { const c=t.code||{}; h+='<div class="step">'+esc(t.step)+'<br><code>'+esc(c.where||'')+'</code> <code>'+esc(c.code||'')+'</code></div>'; });
  h+='</details>';
  if(d.logs){
    h+='<div class="logs"><p>Logs for this call (entries can take a minute or two to appear):</p>';
    d.logs.forEach(l => { h+='<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(l.label)+'</a><pre>'+esc(l.query)+'</pre>'; });
    h+='</div>';
  }
  return h;
}
function checkList(ic){
  let h='<ul class="checks">';
  (ic.checks||[]).forEach(c => { h+='<li class="'+(c.ok?'ok':'bad')+'">'+(c.ok?'&#10003; ':'&#10007; ')+esc(c.name)+(c.detail?' <code>'+esc(c.detail)+'</code>':'')+'</li>'; });
  return h+'</ul>';
}
function jwtPanels(d){
  const j=d.jwt_debug, ic=d.identity_check;
  if(!j && !ic) return '';
  let h='<div class="card jwt"><h3>JWT debug: how Agent 2 knows who the user is</h3>';
  if(j){
    const i=j.iap_jwt||{}, a=j.assertion||{};
    h+='<h4>1. IAP &rarr; web app: the IAP signed JWT (decoded, signature shortened to '+esc(i.signature)+')</h4>';
    h+='<div class="sub">The web app verified it: ES256 signature with the Google IAP keys, iss, aud = '+esc(i.audience_checked)+', not expired</div>';
    h+='<pre>'+esc(JSON.stringify({header:i.header,claims:i.claims},null,2))+'</pre>';
    h+='<h4>2. web app &rarr; Agent 1 &rarr; Agent 2: user assertion signed by '+esc(a.signed_by)+
       (a.tampered?' <span class="REJECTED">(TAMPERED: the user was changed after signing)</span>':'')+'</h4>';
    h+='<div class="sub">raw token (header.payload.signature): valid 60 s, for Agent 2 only, single use. Agent 1 passes it on unchanged.</div>';
    h+='<pre class="raw">'+esc(a.raw)+'</pre>';
    h+='<pre>'+esc(JSON.stringify({header:a.header,claims:a.claims},null,2))+'</pre>';
  }
  if(ic){
    h+='<h4>3. Agent 2 checks the assertion &rarr; <span class="'+(ic.verified?'ALLOW':'REJECTED')+'">'+(ic.verified?'VERIFIED':'REJECTED')+'</span></h4>'+checkList(ic);
    h+='<div class="sub">'+(ic.verified?'user taken from the token: <b>'+esc(ic.user_from_token)+'</b>':esc(ic.reason||''))+'</div>';
  }
  return h+'</div>';
}
function render(d){
  if(d.flow) return renderFlow(d);
  let h = '<p>verdict: <span class="'+esc(d.verdict)+'">'+esc(d.verdict)+'</span></p>';
  if(d.sql) h += '<p>query:</p><pre>'+esc(d.sql)+'</pre><p>rows:</p><pre>'+esc(JSON.stringify(d.rows,null,2))+'</pre>';
  if(d.excerpt!==undefined) h += '<p>site '+esc(d.url)+' (HTTP '+esc(d.status)+')</p><pre>'+esc(d.excerpt)+'</pre>';
  if(d.verdict==='BLOCK' && d.url) h += '<p>'+esc(d.url)+' was blocked.</p>';
  (d.trace||[]).forEach(t => {
    const c = t.code || {};
    h += '<div class="step">'+esc(t.step)+
      (t.verdict ? ' &rarr; <span class="'+esc(t.verdict)+'">'+esc(t.verdict)+'</span>' : '')+
      '<br><code>'+esc(c.where||'')+'</code> <code>'+esc(c.code||'')+'</code></div>';
  });
  return h;
}
async function call(url, body){
  const r = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body||{})});
  const d = await r.json();
  if(!r.ok) throw new Error(d.error || r.statusText);
  return d;
}
async function run(url, target, body){
  const el = document.getElementById(target); el.textContent = 'working...';
  try { el.innerHTML = render(await call(url, body)); } catch(e){ el.textContent = 'error: '+e.message; }
}
function logLinks(logs){
  let h='<div class="logs"><p>Logs for this call (entries can take a minute or two to appear):</p>';
  (logs||[]).forEach(l => { h+='<a href="'+esc(l.url)+'" target="_blank" rel="noopener">'+esc(l.label)+'</a><pre>'+esc(l.query)+'</pre>'; });
  return h+'</div>';
}
function hops(user, rest){
  let h=card(1,'Browser -> IAP','IAP signs you in with your Google account',{user:user});
  h+=arrow('IAP adds request headers')+card(2,'IAP -> web app (Cloud Run)','The web app calls Agent 3 directly',{user:user});
  return h+rest;
}
function renderAsk(d){
  const user=(d.web_header||'').split(':').slice(-1)[0];
  let rest=arrow('Agent Engine API call')+card(3,'web app -> Agent 3','The question',{question:d.question},'',d.code);
  rest+=arrow('Gemini API call, through the gateway (the only outbound call)');
  rest+=card(4,'Agent 3 -> gateway -> Gemini API','Destination: aiplatform.googleapis.com (a Google API). Google runs the search on its side.',
    {model:d.model,endpoint:d.model_endpoint,'search queries Google ran':(d.search_queries||[]).join(' | ')||'(none)'},'ALLOW');
  let h='<p>verdict: <span class="ALLOW">ANSWERED</span></p>'+hops(user,rest);
  h+='<h3>Answer</h3><pre>'+esc(d.answer||'')+'</pre>';
  if((d.sources||[]).length){ h+='<p>Sources Google used (a click here is your browser, not the agent):</p><ul>';
    d.sources.forEach(s => { h+='<li>'+esc(s.title||s.uri)+'</li>'; }); h+='</ul>'; }
  h+='<details open><summary>Agent 3 tools and code</summary>';
  (d.tools||[]).forEach(t => { h+='<div class="step"><b>'+esc(t.name)+'</b>: '+esc(t.description)+'<br><code>'+esc((t.code||{}).where||'')+'</code> <code>'+esc((t.code||{}).code||'')+'</code></div>'; });
  h+='<div class="step">The agent passes the tool to Gemini; it has no other way out.<br><code>'+esc((d.code||{}).where||'')+'</code></div></details>';
  return h+logLinks(d.logs);
}
function renderOpen(d){
  const user=(d.web_header||'').split(':').slice(-1)[0];
  const env=JSON.stringify(d.runtime_proxy_env||{});
  let rest=arrow('Agent Engine API call')+card(3,'web app -> Agent 3','Agent 3 is asked to open a website',{url:d.url,'proxy settings in the agent':env==='{}'?'none':env},'',d.code);
  rest+=arrow('plain HTTP request; the network sends it to the gateway');
  rest+=card(4,'Agent 3 -> gateway -> '+d.url, d.verdict==='DENIED'?'The gateway refused the request; it never reached the website':'The request reached the website',
    {'HTTP status':d.status, response:d.excerpt||d.error||''}, d.verdict);
  return '<p>verdict: <span class="'+esc(d.verdict)+'">'+esc(d.verdict)+'</span></p>'+hops(user,rest)+logLinks(d.logs);
}
async function runTo(url, target, body){
  const el = document.getElementById(target); el.textContent = 'working...';
  try { const d=await call(url, body); el.innerHTML = d.answer!==undefined ? renderAsk(d) : renderOpen(d); }
  catch(e){ el.textContent = 'error: '+e.message; }
}
</script></body></html>"""


@app.get("/")
def index():
    email, cookie = identity()
    name = email or "unknown"
    return (PAGE.replace("__NAME__", html.escape(name))
                .replace("__COOKIE__", html.escape(cookie or "(no cookie header)"))
                .replace("__A1_POLICY__", html.escape(A1_POLICY)))


def _call(method, extra=None, **kwargs):
    try:
        result = getattr(agent1(), method)(**kwargs)
        result["web_header"] = request.headers.get("X-Goog-Authenticated-User-Email", "")
        result.update(extra or {})
        return jsonify(result)
    except Exception as exc:  # surface agent errors on the page
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502


def _call_as_user(method, extra=None, tamper=False, **kwargs):
    """Verify the IAP user, sign the assertion, then call Agent 1 with it."""
    try:
        user, assertion, jwt_debug = user_assertion(tamper)
    except PermissionError as exc:
        return jsonify({"error": f"identity check failed in the web app: {exc}"}), 401
    except Exception as exc:  # signing failures etc.
        return jsonify({"error": f"could not sign the user assertion: {type(exc).__name__}: {exc}"}), 502
    return _call(method, extra=dict(extra or {}, jwt_debug=jwt_debug), email=user, assertion=assertion, **kwargs)


@app.post("/api/move-cookie")
def move_cookie():
    _, cookie = identity()
    return _call_as_user("move_cookie", cookie=cookie)


@app.post("/api/query-db")
def query_db():
    _, cookie = identity()
    tamper = bool((request.get_json(silent=True) or {}).get("tamper"))
    return _call_as_user("query_db", tamper=tamper, cookie=cookie)


S4_ENGINES = {"A2": AGENT2.rsplit("/", 1)[-1], "A3": AGENT3.rsplit("/", 1)[-1]}
S4_ENDPOINTS = {"A2": AGENT2_ENDPOINT, "A3": AGENT3_ENDPOINT}


def _log_link(label, query):
    url = (f"https://console.cloud.google.com/logs/query;query={quote(query, safe='')}"
           f";timeRange=PT1H?project={PROJECT}")
    return {"label": label, "query": query, "url": url}


def _s4_logs(target, since):
    agent1_id = AGENT1.rsplit("/", 1)[-1]
    ts = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    return [
        _log_link("IAP decision (allowed or denied)",
                  'protoPayload.serviceName="iap.googleapis.com"\n'
                  f'protoPayload.metadata.dryRun=false\n'
                  f'"{agent1_id}"\n"{S4_ENDPOINTS[target]}"\ntimestamp>="{ts}"'),
        _log_link("Gateway request log",
                  'resource.type="networkservices.googleapis.com/Gateway"\n'
                  f'resource.labels.gateway_name="{GATEWAY}"\n'
                  f'httpRequest.requestUrl:"reasoningEngines/{S4_ENGINES[target]}"\ntimestamp>="{ts}"'),
    ]


@app.post("/api/call-agent")
def call_agent():
    target = (request.get_json(silent=True) or {}).get("target", "")
    if target not in S4_ENGINES:
        return jsonify({"error": "target must be A2 or A3"}), 400
    since = datetime.now(timezone.utc) - timedelta(seconds=30)
    if target == "A3":
        # no user assertion here: the decision is the gateway policy's alone
        email, _ = identity()
        note = {"policy": A1_POLICY, "rule": "A1 may NOT call A3", "effect": "DENY",
                "bound_to": GATEWAY,
                "text": "The gateway stopped this call. Agent 3 was never reached, and no user token was involved."}
        return _call("call_agent", extra={"logs": _s4_logs(target, since), "policy_note": note},
                     target=target, email=email)
    return _call_as_user("call_agent", extra={"logs": _s4_logs(target, since)}, target=target)


def _a3_logs(since, host=None):
    a3_id = AGENT3.rsplit("/", 1)[-1]
    ts = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    iap = ('protoPayload.serviceName="iap.googleapis.com"\n'
           f'"{a3_id}"\n' + (f'"{host}"\n' if host else "") + f'timestamp>="{ts}"')
    logs = [_log_link("IAP decisions for Agent 3 (granted or denied, with destination)", iap)]
    if not host:
        logs.append(_log_link("Gateway request log: the Gemini call",
                              'resource.type="networkservices.googleapis.com/Gateway"\n'
                              f'resource.labels.gateway_name="{GATEWAY}"\n'
                              f'httpRequest.requestUrl:"generateContent"\ntimestamp>="{ts}"'))
    return logs


def _call_a3(method, extra, **kwargs):
    try:
        result = getattr(engine(AGENT3), method)(**kwargs)
        result["web_header"] = request.headers.get("X-Goog-Authenticated-User-Email", "")
        result.update(extra)
        return jsonify(result)
    except Exception as exc:  # surface agent errors on the page
        return jsonify({"error": f"{type(exc).__name__}: {exc}"}), 502


@app.post("/api/ask")
def ask():
    question = ((request.get_json(silent=True) or {}).get("question") or "").strip()[:500]
    if not question:
        return jsonify({"error": "type a question"}), 400
    since = datetime.now(timezone.utc) - timedelta(seconds=30)
    return _call_a3("ask", {"question": question, "logs": _a3_logs(since)}, question=question)


@app.post("/api/open-website")
def open_website():
    url = ((request.get_json(silent=True) or {}).get("url") or "").strip()[:300]
    if not url:
        return jsonify({"error": "type a website"}), 400
    host = re.sub(r"^https?://", "", url).split("/")[0].lower()
    since = datetime.now(timezone.utc) - timedelta(seconds=30)
    return _call_a3("open_website", {"logs": _a3_logs(since, host)}, url=url)
