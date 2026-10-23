# Authorized Store snapshot evaluation

Current metadata behavior is extended by [SCRUM-38](store-v1-metadata-preservation.md):
use its field map for connector/type/billing fields, README/embedded evidence and
version projections. Earlier exclusion statements below describe prior checkpoints.
Access/publication gates and historical verification claims remain unchanged.

Use a short-lived **access token** from your own authorized Store login for local,
read-only testing, not as a production service credential. The unchanged
`HedgeApiClient` accepts the token file; it does not depend on a particular OAuth
grant. Actual acceptance depends on token audience/permissions and expiry, which
must be tested. A signed-in UI session alone does not prove backend access.
No cookie extraction, automated login, refresh, proxy or authentication subsystem
is needed. Use only the login provider's authorized token export/manual mechanism;
if unavailable, import a locally saved authorized JSON response instead.

## Exact setup

1. In your own signed-in Chrome Store tab, open **DevTools → Network**, leave
   **Preserve log** off, and clear the list. Navigate to App Explorer or open an
   App's details to trigger a read-only request. Filter for `app/all` or the
   selected App's `/app/` request; verify the URL belongs to
   `https://store.haslab-dataspace.pt/backend/api/v1` and the method is GET.
2. Select that request → **Headers → Request Headers → Authorization**. If it
   contains `Bearer …`, manually copy that header's value using Chrome's **Copy
   value**. Do not use Copy as cURL, export HAR, copy cookies, run console scripts
   or inspect refresh tokens. If there is no Bearer header, use the authorized
   JSON response-body fallback below; do not derive credentials from the session.
3. Open your normal SSH terminal to this development server. Run the following
   **on the server**, then paste the copied value only at the hidden prompt. It
   accepts either the raw access token or a value with the `Bearer ` prefix.

```sh
install -d -m 700 /home/ubuntu/.config/hedge
python3 - <<'PYTOKEN'
import getpass, os, re, sys, warnings
from pathlib import Path
if not sys.stderr.isatty():
    raise SystemExit("Use an interactive SSH terminal; token entry must be hidden")
warnings.simplefilter("error", getpass.GetPassWarning)
token = getpass.getpass("Temporary Store access token (hidden): ").strip()
if token.startswith("Bearer "):
    token = token[7:]
if len(token) > 16384 or not re.fullmatch(r"[A-Za-z0-9._~+/\-]+=*", token):
    raise SystemExit("Invalid token format; nothing saved")
path = Path('/home/ubuntu/.config/hedge/store-access-token')
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
with os.fdopen(fd, 'w') as handle:
    os.fchmod(handle.fileno(), 0o600)
    handle.write(token + '\n')
print("Private token file saved; contents not displayed")
PYTOKEN
```

The token travels over your SSH connection and never appears in the shell command
or terminal echo. Clear your clipboard after saving, avoid screen recordings, and
never paste it into chat, shell arguments/history, environment variables or Git.
The launcher requires an owned regular private file outside this checkout;
symlink files and group/world permissions are rejected. Do not use a refresh or
ID token. Replace expired tokens manually, then stop/restart your own evaluation;
there is no renewal implementation.

Start a separate Chat Pane (8091 may already be occupied):

```sh
cd /home/ubuntu/hedge
bash scripts/store-v1-playground.sh --browser --port 8093 \
  --store-token-file /home/ubuntu/.config/hedge/store-access-token \
  --store-id 56779afa-bdcc-4abe-a8b0-d306dc07bed1
```

Open **http://127.0.0.1:8093**; for remote access use the existing guide's SSH
loopback forwarding. Optionally add `--embeddings` before input options for real
pinned E5, subject to the [model/resource limitations](store-v1-browser-evaluation.md).
The default exercises real PostgreSQL lexical retrieval and regex NLU, not
simulated embeddings or generation. `--rasa` remains experimental. Ollama is not
used: responses remain supplied-field quotations.

The launcher first starts one bounded, disposable outbound process with the
private file mounted read-only. It uses the existing client to GET `getAllApps`
and one eligible App's `getApp`. Only safe counts/statuses are reported; no
headers, token, response text, names or native IDs are logged by this helper.
`getApp` is diagnostic: its later response does not replace snapshot records;
404 indicates disappearance, not authority to retire Apps. `getAssets` is not
needed for App recommendations and is not requested or joined in this path.

After fetching, that process exits. The Chat Pane receives only a reduced source
input: known App/version fields, with owner/contact and embedded Asset metadata
removed. The private token is **never mounted into the chat runner**. Temporary
input is mode 0600, outside Git/build context, and removed on launcher exit.
PostgreSQL, Qdrant and Valkey use unique disposable resources. Only explicitly
`active=true` and `visible=true` Apps appear in cards, names/context or source-record
inspection. README is retained in the local source model but remains untrusted,
excluded from search/explanations. Source data is escaped, not treated as instructions.

All inputs use `snapshot_complete=False`. Empty, malformed, duplicate, wrong-Store
or wholly ineligible inputs fail before catalogue bootstrap; failures never
silently select fixtures. Explicit publication withdrawal remains a source fact;
absence never authorizes retirement. Each startup requires a fresh database.
There is no schedule, production index, public Store result or ongoing Store polling.
Private records/history exist only for this run: do not capture them in shared
screenshots, browser regression artifacts, Git or logs. Run artifact-producing
browser regressions with sanitized fixtures only.

Evaluate actual names/search needs in the status panel, then ordinal details,
comparisons, reload/context, unsupported prices/protocols and reset. These source
facts are an account-scoped snapshot, not proof of complete/public catalogue
coverage, data reuse rights, or current live publication after fetching.

## Local JSON fallback and cleanup

If the authorized token cannot be obtained or is rejected (401/403), use a private,
locally saved `getAllApps` array or `getApp` object. Do not automatically retry with
browser cookies or weaker authentication. In Chrome **Network → selected authorized GET → Response**, manually copy only
its JSON response body. Save it with a local editor to a mode-0600 file outside
any checkout; transfer with `scp -p` over SSH if necessary. Never export HAR or
request headers. Protect the server copy with mode 0600, then start:

```sh
bash scripts/store-v1-playground.sh --browser --port 8093 \
  --apps-json /home/ubuntu/.config/hedge/apps.json \
  --store-id 56779afa-bdcc-4abe-a8b0-d306dc07bed1
```

This runs identical normalization/reconciliation/retrieval/dialogue. The UI labels
JSON import separately from API fetching and authored fixtures. It proves payload
compatibility and local wiring, not transport/authentication. The file stays
private and is never committed. Stop with Ctrl-C; only this run's resources are
removed. Delete your private token/JSON manually when no longer needed. For an
abandoned run, use the existing [narrow cleanup procedure](store-v1-browser-evaluation.md);
do not stop another evaluation, the frozen demo, or prune resources broadly.

## Initial preparation evidence (2026-10-12, `df073c1`)

From this development host, unauthenticated GET of OpenAPI returned **200** and
`getAllApps` returned **401**. The current public specification still declares
required Authorization headers for `getAllApps` and `getApp`. Verified **479 unit tests**, **53 focused disposable PostgreSQL/Qdrant tests**,
and actual Chromium multi-turn checks passed using sanitized imported records,
a different Store ID and an unpublished sentinel. Shared-package branch coverage
was **92.46%**; this is not whole-project coverage or a proposal KPI result.
Ruff, shell/JavaScript syntax, whitespace and documentation-link checks passed.
Offline regressions
exercise the unchanged HTTPS client with a fake file token, success/401/403,
detail 404, source-field reduction and conservative completeness. These mocked
responses do not establish that a real user token is accepted. At that preparation checkpoint the user had not supplied a token; **no
authenticated Store requests were made by the agent**. Authenticated execution requires the locally supplied token; record only
statuses/counts and the tested mode, never tokens or raw responses. No
authenticated success is claimed without running it.

Dedicated HEDGE backend credentials remain necessary for unattended operation,
renewal/rotation, approved visibility scope and operational ownership. Snapshot
completeness/public corpus rights, native Angular integration and proposal KPI
acceptance remain separate gates in the [baseline](integration-baseline.md).


## First authorized snapshot and browsing (2026-10-12)

The user reports successful `getAllApps` and `getApp` **HTTP 200**, with two real,
eligible Apps and working named details/source comparisons. Inspection of the
existing isolated run confirms `authorized-api-snapshot`, two eligible records
and lexical-only retrieval. This is an account-scoped smoke test, not complete
catalogue, production service-credential or native UI acceptance.

Catalogue requests such as `Show me all available applications`, `List Apps`,
`Browse the catalogue` and `What applications are available?` now use the existing
Store-only PostgreSQL resolver rather than searching generic catalogue words.
Results retain native Store/App identity, are bounded to **five**, ordered stably
by native App ID, and labelled `catalogue` rather than dense/lexical relevance.
The response always states that the snapshot may be incomplete. Prices and
unsupported filters remain limited; requests containing domain constraints or
negation stay on the existing search path. Browsing uses a small compositional
English grammar, not a new global classifier or multilingual acceptance claim.

Every browse rereads current PostgreSQL publication and metadata for identities
present in this isolated snapshot, including initially unpublished Apps that
later become eligible locally. Withdrawn/inactive Apps and other Stores cannot
enter results. Returned order becomes conversation context for ordinal details,
comparisons and reload; empty lists clear old references. This represents current
**local** snapshot eligibility, not ongoing live Store freshness.

Real pinned E5 was verified against that same private authorized snapshot in a
**separate JSON-import run**, without reading the token or repeating Store requests:

| Check | Observed result |
|---|---|
| Catalogue browsing | 2 currently eligible Apps; `catalogue` evidence, incomplete-snapshot caveat |
| Named-App search | 2 results, each with actual `dense` and `lexical` retrieval evidence |
| Conceptual query (`organizing semantic information`) | 2 `dense` candidates, 0 lexical matches; actual vector retrieval, not lexical fallback |
| Follow-ups | Ordinal detail, source comparison, reload/context and missing-price limitation passed through Chromium |

No private record contents, native IDs, screenshots, traces or tokens were retained
in browser artifacts. The two-record corpus and existing tokenizer-regex warning
still prevent retrieval-quality/model-compatibility acceptance; nearest neighbours
are candidates, not proven relevant recommendations. Generation remains source
quotations, with no Ollama/LLM changes.

The check exposed a developer-image permission defect: private-input runs use the
host UID, while saved E5 weights were mode 0600 under the image UID. The launcher
now makes **only the public pinned model artifact** readable across those UIDs.
Token/snapshot permissions remain private. Neither the model pin nor dependencies
or retrieval algorithm changed.

Regression evidence: **497 unit tests**, **54 focused isolated PostgreSQL/Qdrant
checks**, and sanitized Chromium multi-turn regressions passed (shared branch
coverage **92.46%**). Browsing tests include bounded results, domain-search
separation, current metadata, withdrawal/reappearance, another Store, empty
publication and conversation references. Ruff, Bash/JavaScript syntax and
whitespace/link checks passed.

For a private snapshot that has already been fetched, start without another Store
request using the original run's mounted input path (inspect only that mount):

```sh
snapshot_path=$(docker inspect "hedge-store-cli-tmp.<your-run>-runner" \
  --format '{{range .Mounts}}{{if eq .Destination "/input/apps.json"}}{{.Source}}{{end}}{{end}}')
bash scripts/store-v1-playground.sh --browser --embeddings --port 8094 \
  --apps-json "$snapshot_path" --store-id 56779afa-bdcc-4abe-a8b0-d306dc07bed1
```

Use an unused loopback port; the original run stays independent. A running Python
process needs restart to load policy changes. Stop/restart only your own evaluation
when desired, never the frozen demo. If E5 resources are unavailable, omit
`--embeddings`; catalogue browsing does not need vectors and the lexical path
remains available. The launcher cleans only its unique disposable resources.
