---
name: web-fetch
description: Pull URLs and call external HTTP APIs.
category: workflow
common: 0
trigger_keywords: fetch URL, http, web, download, api call, curl
trigger_use_when: retrieving content from a URL or hitting an external API
---
# web-fetch

Pull URLs and call external HTTP APIs. The network tools render in your
TOOLS section when this skill is granted.

## When to reach for it
Retrieving a page, or calling an external HTTP API. The tools: url_fetch,
http_get, http_post.

## Workflow

**Read a page**
1. url_fetch the URL — returns the text body.
2. If the body is HTML, summarize it — do not echo raw HTML back.

**Call an API**
1. http_get or http_post, headers set as the API needs.
2. Inspect status: 2xx — parse the body; 4xx — surface the error; 5xx —
   retry once, then surface.

## Never
- Paste a whole page into a reply — summarize.
- Put credentials in the URL — use the headers parameter.
- Reach substrate endpoints with these tools — the api_* tools and MEMORY
  PROTOCOL are for that; web-fetch is for the outside world.

## Stop
- After a 4xx — surface it to the operator.
- After two failed retries — surface it.
