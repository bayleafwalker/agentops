# Vuoro Cloud plugin connection

This package defines one portable remote MCP server and one read workflow.
The server URL is `https://api.vuoro.cloud/mcp`. It requires a Vuoro OAuth
grant for one workspace. The package contains no credential.

As of 2026-09-29, Vuoro Cloud has a registered `claude-connector` client and a
live read surface (`list_ready_work`, `describe_work`). A separate ChatGPT
client is not registered. ChatGPT installation therefore depends on a Vuoro
Cloud client registration and a ChatGPT developer-mode connection. Do not use
the Claude client secret for ChatGPT.

Register `chatgpt-connector` as a confidential OAuth client in Vuoro Cloud's
clients file, following its credential-rotation runbook. Give it a distinct
secret hash and the exact redirect URI shown by ChatGPT's MCP management page.
Vuoro's live OAuth metadata advertises RFC 9207 issuer identification, so the
expected stable redirect is
`https://chatgpt.com/connector_platform_oauth_redirect`; use the page's exact
value if it differs. Keep the secret outside Git. Configure the connection in
ChatGPT developer mode with this client ID and secret, the MCP URL above, and
only `vuoro:work.read` scope. Vuoro's current scope matrix grants that scope
to a registered human client with active membership; it does not grant the
record or claim scopes to `chatgpt-connector`.

The first end-to-end check is a ChatGPT request to list ready work, followed by
`describe_work` for a known work ID. Compare both answers with Vuoro's served
state, and test that a different workspace's work is not visible. A prompt
such as “Continue cred-broker release work” is a later acceptance case: the
current two read tools cannot search all work or reconstruct run, evidence,
and decision history.

The plugin deliberately advertises only read capability. Vuoro's E2 record
and claim tools need their owning work item to land and a separate host test
before this package can teach a write workflow. Effect acceptance and effect
application remain outside the published MCP surface.
