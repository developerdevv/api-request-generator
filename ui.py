INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>API Request Generator</title>
<style>
  body{font-family:system-ui,sans-serif;max-width:820px;margin:32px auto;padding:0 16px;background:#0f1115;color:#e6e6e6}
  h1{font-size:1.5rem;margin-bottom:4px} p.sub{color:#9aa0a6;margin-top:0}
  label{display:block;margin:14px 0 4px;font-size:.85rem;color:#9aa0a6}
  textarea,input{width:100%;box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #2a2f3a;background:#171a21;color:#e6e6e6;font:inherit}
  textarea{min-height:90px}
  button{padding:10px 18px;border:0;border-radius:8px;background:#4f7cff;color:#fff;font:inherit;cursor:pointer;margin-top:16px}
  button:disabled{opacity:.5} .tabs button{background:#232836;margin:12px 6px 0 0;padding:6px 12px;font-size:.85rem}
  .tabs button.on{background:#4f7cff}
  pre{background:#171a21;border:1px solid #2a2f3a;border-radius:8px;padding:12px;overflow:auto;white-space:pre-wrap;word-break:break-all}
  .badge{display:inline-block;padding:2px 10px;border-radius:6px;background:#2f9e6b;font-weight:600;margin-right:8px}
  #err{color:#ff6b6b;margin-top:12px} table{width:100%;border-collapse:collapse;margin-top:6px}
  td{border-bottom:1px solid #2a2f3a;padding:6px;font-family:monospace;font-size:.85rem;word-break:break-all}
  a{color:#7aa2ff}
</style>
</head>
<body>
<h1>API Request Generator</h1>
<p class="sub">Describe an API call in plain English. Get a ready-to-run request. <a href="/docs">API docs</a></p>

<label>Your API key (sent as X-API-Key)</label>
<input id="key" type="password" placeholder="rg_...">
<label>What do you want to call?</label>
<textarea id="prompt" placeholder="Create a new GitHub issue titled 'Login bug' in repo devv/demo-app"></textarea>
<label>Webhook URL (optional, https only)</label>
<input id="hook" placeholder="https://...">
<button id="go" onclick="gen()">Generate</button>
<div id="err"></div>

<div id="out" hidden>
  <h3><span class="badge" id="method"></span><span id="url" style="font-family:monospace;word-break:break-all"></span></h3>
  <p id="expl"></p>
  <b>Headers</b><table id="hdrs"></table>
  <b>Body</b><pre id="body"></pre>
  <div class="tabs">
    <button class="on" onclick="tab('curl',this)">cURL</button>
    <button onclick="tab('js',this)">fetch</button>
    <button onclick="tab('py',this)">Python</button>
    <button onclick="copy()">Copy</button>
  </div>
  <pre id="snip"></pre>
</div>

<script>
const $ = id => document.getElementById(id);
let snippets = {}, current = 'curl';
$('key').value = sessionStorage.getItem('k') || '';

function tab(name, el){
  current = name;
  document.querySelectorAll('.tabs button').forEach(b => b.classList.remove('on'));
  el.classList.add('on');
  $('snip').textContent = snippets[name];
}
function copy(){ navigator.clipboard.writeText(snippets[current]); }

async function gen(){
  $('go').disabled = true; $('err').textContent = ''; $('out').hidden = true;
  sessionStorage.setItem('k', $('key').value);
  try{
    const payload = {prompt: $('prompt').value};
    const hook = $('hook').value.trim();
    if(hook) payload.webhook_url = hook;
    const r = await fetch('/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'X-API-Key': $('key').value},
      body: JSON.stringify(payload)
    });
    const d = await r.json();
    if(!r.ok) throw new Error(typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail));
    render(d);
  }catch(e){ $('err').textContent = e.message; }
  $('go').disabled = false;
}

function render(d){
  let url = d.url;
  try{
    const u = new URL(d.url);
    d.query_params.forEach(p => u.searchParams.append(p.key, p.value));
    url = u.toString();
  }catch(e){}
  $('method').textContent = d.method;
  $('url').textContent = url;
  $('expl').textContent = d.explanation;
  $('hdrs').textContent = '';
  d.headers.forEach(h => {
    const tr = document.createElement('tr');
    [h.key, h.value].forEach(t => { const td = document.createElement('td'); td.textContent = t; tr.appendChild(td); });
    $('hdrs').appendChild(tr);
  });
  let pretty = d.body || '(no body)';
  try{ pretty = JSON.stringify(JSON.parse(d.body), null, 2); }catch(e){}
  $('body').textContent = pretty;

  const hdrObj = Object.fromEntries(d.headers.map(h => [h.key, h.value]));
  const curl = ['curl -X ' + d.method + " '" + url + "'"]
    .concat(d.headers.map(h => "-H '" + h.key + ': ' + h.value + "'"));
  if(d.body) curl.push("-d '" + d.body + "'");
  snippets.curl = curl.join(' \\\n  ');
  snippets.js = 'fetch(' + JSON.stringify(url) + ', {\n  method: ' + JSON.stringify(d.method) +
    ',\n  headers: ' + JSON.stringify(hdrObj, null, 2) +
    (d.body ? ',\n  body: ' + JSON.stringify(d.body) : '') + '\n}).then(r => r.json()).then(console.log);';
  snippets.py = 'import requests\n\nr = requests.request(\n    ' + JSON.stringify(d.method) + ',\n    ' + JSON.stringify(url) +
    ',\n    headers=' + JSON.stringify(hdrObj) +
    (d.body ? ',\n    data=' + JSON.stringify(d.body) : '') + '\n)\nprint(r.status_code, r.text)';
  current = 'curl';
  document.querySelectorAll('.tabs button').forEach((b, i) => b.classList.toggle('on', i === 0));
  $('snip').textContent = snippets.curl;
  $('out').hidden = false;
}
</script>
</body>
</html>
"""