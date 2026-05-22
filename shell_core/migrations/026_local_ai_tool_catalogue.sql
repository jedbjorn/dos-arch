-- 026 — local-AI tool catalogue: 25 tool rows, 3 skills, git-workflow triggers.
--
-- The handler subsystem (shell_core/services/tools/, PR #72) is inert until
-- tool rows reference it. This migration is that wiring for already-
-- bootstrapped DBs; a fresh install gets the same rows from assets/tools/
-- and assets/skills/ via seed_from_assets (migrations are stamped, not run,
-- on a fresh bootstrap). The two paths are generated from one definition
-- set so they cannot drift.
--
-- Tool -> skill scoping is by handler-family prefix (file.* -> file-ops,
-- proc.* -> process-exec, git.* -> git-workflow, net.* -> web-fetch); the
-- UPDATEs at the end apply it. api_* tools keep handler 'api' and stay
-- general. No shell is granted the new skills here — that is deliberate
-- per-shell work (shell_skills), done after this lands.
--
-- psutil / httpx are NOT inserted into dr_dependencies: that catalogue is
-- auto-synced from the venv by dr_sync (httpx is already a row).
--
-- Plain SQL: migrate.py owns the transaction and the schema_migrations row.

-- ── skills ───────────────────────────────────────────────────────────────
INSERT INTO skills (name, description, category, common, content, trigger_keywords, trigger_use_when) VALUES (
  'file-ops', 'Read, edit, search, and author files in the working directory.', 'workflow', 0, '# file-ops

Read, edit, search, and author files in the working directory. The file
tools render in your TOOLS section when this skill is granted.

## When to reach for it
Reading, editing, writing, or searching files. The tools: file_read,
file_write, file_edit, file_append, file_list, file_search, file_find,
file_delete, file_move.

## Workflow

**Find the thing**
1. file_search (contents) or file_find (names) — narrow to candidates.
2. file_read with a line range — confirm before acting.

**Edit the thing**
1. file_read first — see the current content.
2. file_edit with a unique old_str — a non-unique match is rejected, not
   guessed at; add surrounding context until it is unique.
3. file_read the edited region — verify.

**Create the thing**
1. file_find to confirm it does not already exist.
2. file_write — it fails if the path is already there; use file_edit for an
   existing file.

## Never
- file_edit blind — always file_read first.
- file_delete without naming, in the same reply, what is being deleted and
  why. file_delete refuses a directory; it is a single-file tool.
- file_write to a path you have not confirmed is absent.

## Stop
- After a destructive op (delete, move) — announce it; do not chain.
- After an edit and its verification — announce the result; do not chain.
',
  'read file, edit file, write file, search files, find file', 'reading, editing, or searching files in the working directory');
INSERT INTO skills (name, description, category, common, content, trigger_keywords, trigger_use_when) VALUES (
  'process-exec', 'Run commands and inspect processes in the working directory.', 'workflow', 0, '# process-exec

Run commands and inspect processes from the working directory. The process
tools render in your TOOLS section when this skill is granted.

## When to reach for it
Running a build, a test, or any command; checking or stopping a process.
The tools: exec, exec_bg, proc_check, proc_kill, proc_list.

## Workflow

**Synchronous work**
1. exec with argv as a list, never a string — there is no shell, so a
   command like `echo a b` must be `["echo", "a", "b"]`.
2. Read exit_code: 0 is success; non-zero — inspect stderr.
3. On timeout, retry once with a larger timeout (ceiling 300s); then
   surface it.

**Long-running work**
1. exec_bg — returns a pid and a log path.
2. proc_check the pid until it reports not running.
3. Read the log path for the captured output.

## Never
- exec with shell metacharacters expecting expansion — argv is literal, not
  a shell line. A pipe or a glob is a literal argument.
- proc_kill with SIGKILL as a first move — SIGTERM first, SIGKILL only if
  the process does not exit.

## Stop
- After a non-zero exit — surface it to the operator.
- After a timeout twice — surface it.
- After a kill — announce it; do not chain.
',
  'run, execute, command, build, test, compile, npm, make', 'running a build, test, or other command in the working dir');
INSERT INTO skills (name, description, category, common, content, trigger_keywords, trigger_use_when) VALUES (
  'web-fetch', 'Pull URLs and call external HTTP APIs.', 'workflow', 0, '# web-fetch

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
',
  'fetch URL, http, web, download, api call, curl', 'retrieving content from a URL or hitting an external API');

-- git-workflow already exists — add its trigger metadata.
UPDATE skills SET trigger_keywords = 'commit, branch, PR, stacked, rebase, push, diff, log', trigger_use_when = 'committing, branching, inspecting, or pushing a git repository'
  WHERE name = 'git-workflow';

-- ── tools ────────────────────────────────────────────────────────────────
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_read', 'Read a file from the working directory.', 'builtin', '{"type": "object", "properties": {"path": {"type": "string", "description": "file path, ~ is expanded"}, "lines": {"type": "array", "items": {"type": "integer"}, "description": "optional [start, end] line numbers, 1-based inclusive"}}, "required": ["path"]}', 'file.read');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_write', 'Write a new file. Fails if the path already exists.', 'builtin', '{"type": "object", "properties": {"path": {"type": "string", "description": "file path to create"}, "content": {"type": "string", "description": "full file content"}}, "required": ["path", "content"]}', 'file.write');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_edit', 'Replace a unique string in an existing file.', 'builtin', '{"type": "object", "properties": {"path": {"type": "string", "description": "file to edit"}, "old_str": {"type": "string", "description": "exact text to replace, must occur exactly once"}, "new_str": {"type": "string", "description": "replacement text"}}, "required": ["path", "old_str", "new_str"]}', 'file.edit');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_append', 'Append content to the end of an existing file.', 'builtin', '{"type": "object", "properties": {"path": {"type": "string", "description": "file to append to"}, "content": {"type": "string", "description": "text to append"}}, "required": ["path", "content"]}', 'file.append');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_list', 'List the entries of a directory.', 'builtin', '{"type": "object", "properties": {"path": {"type": "string", "description": "directory path"}, "recursive": {"type": "boolean", "description": "recurse into subdirectories"}}, "required": ["path"]}', 'file.list');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_search', 'Search file contents for a pattern.', 'builtin', '{"type": "object", "properties": {"pattern": {"type": "string", "description": "substring, or a regex when regex is true"}, "path": {"type": "string", "description": "file or directory to search, defaults to the working dir"}, "regex": {"type": "boolean", "description": "treat pattern as a regular expression"}}, "required": ["pattern"]}', 'file.search');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_find', 'Find files by name using glob semantics.', 'builtin', '{"type": "object", "properties": {"name_pattern": {"type": "string", "description": "glob pattern, e.g. *.py"}, "path": {"type": "string", "description": "directory to search under, defaults to the working dir"}}, "required": ["name_pattern"]}', 'file.find');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_delete', 'Delete a file. Destructive. Refuses a directory.', 'builtin', '{"type": "object", "properties": {"path": {"type": "string", "description": "file to delete"}}, "required": ["path"]}', 'file.delete');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'file_move', 'Move or rename a file.', 'builtin', '{"type": "object", "properties": {"src": {"type": "string", "description": "source path"}, "dst": {"type": "string", "description": "destination path"}}, "required": ["src", "dst"]}', 'file.move');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'exec', 'Run a command synchronously and capture its output.', 'builtin', '{"type": "object", "properties": {"argv": {"type": "array", "items": {"type": "string"}, "description": "command and arguments as a list, no shell"}, "cwd": {"type": "string", "description": "working directory, defaults to the dispatcher cwd"}, "timeout": {"type": "integer", "description": "seconds before timeout, ceiling 300"}}, "required": ["argv"]}', 'proc.exec');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'exec_bg', 'Run a command in the background. Returns its pid.', 'builtin', '{"type": "object", "properties": {"argv": {"type": "array", "items": {"type": "string"}, "description": "command and arguments as a list, no shell"}, "cwd": {"type": "string", "description": "working directory, defaults to the dispatcher cwd"}}, "required": ["argv"]}', 'proc.exec_bg');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'proc_check', 'Check whether a process is running.', 'builtin', '{"type": "object", "properties": {"pid": {"type": "integer", "description": "process id to check"}}, "required": ["pid"]}', 'proc.check');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'proc_kill', 'Send a signal to a process. Destructive.', 'builtin', '{"type": "object", "properties": {"pid": {"type": "integer", "description": "process id to signal"}, "signal": {"type": "string", "description": "signal name, defaults to SIGTERM"}}, "required": ["pid"]}', 'proc.kill');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'proc_list', 'List running processes, optionally name-filtered.', 'builtin', '{"type": "object", "properties": {"name_filter": {"type": "string", "description": "optional substring to match against process names"}}, "required": []}', 'proc.list');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_status', 'Show the working-tree status of a repository.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}}, "required": ["cwd"]}', 'git.status');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_diff', 'Show the diff of a repository, working tree or staged.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}, "staged": {"type": "boolean", "description": "show the staged diff instead of the working tree"}, "path": {"type": "string", "description": "limit the diff to this path"}}, "required": ["cwd"]}', 'git.diff');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_log', 'Show recent commits of a repository.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}, "n": {"type": "integer", "description": "number of commits, defaults to 10"}, "path": {"type": "string", "description": "limit the log to this path"}}, "required": ["cwd"]}', 'git.log');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_branch', 'List the local branches of a repository.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}}, "required": ["cwd"]}', 'git.branch');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_commit', 'Commit staged changes with a message.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}, "message": {"type": "string", "description": "commit message"}, "stage_all": {"type": "boolean", "description": "stage every change before committing"}}, "required": ["cwd", "message"]}', 'git.commit');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_checkout', 'Switch to a branch, or create one.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}, "branch": {"type": "string", "description": "branch name"}, "create": {"type": "boolean", "description": "create the branch before switching"}}, "required": ["cwd", "branch"]}', 'git.checkout');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_pull', 'Pull from upstream. Fast-forward only by default.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}, "rebase": {"type": "boolean", "description": "rebase instead of fast-forward"}}, "required": ["cwd"]}', 'git.pull');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'git_push', 'Push commits to upstream.', 'builtin', '{"type": "object", "properties": {"cwd": {"type": "string", "description": "repository working directory"}, "force": {"type": "boolean", "description": "force-with-lease the push"}}, "required": ["cwd"]}', 'git.push');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'http_get', 'HTTP GET. Returns status, headers, and body.', 'builtin', '{"type": "object", "properties": {"url": {"type": "string", "description": "absolute URL"}, "headers": {"type": "object", "description": "optional request headers"}}, "required": ["url"]}', 'net.http_get');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'http_post', 'HTTP POST with a body or a JSON payload.', 'builtin', '{"type": "object", "properties": {"url": {"type": "string", "description": "absolute URL"}, "body": {"type": "string", "description": "optional raw request body"}, "json": {"type": "object", "description": "optional JSON request body"}, "headers": {"type": "object", "description": "optional request headers"}}, "required": ["url"]}', 'net.http_post');
INSERT INTO tools (name, description, kind, spec, handler) VALUES (
  'url_fetch', 'Fetch a URL and return its plain-text body.', 'builtin', '{"type": "object", "properties": {"url": {"type": "string", "description": "absolute URL"}}, "required": ["url"]}', 'net.url_fetch');

-- ── scope each tool to its skill, by handler-family prefix ───────────────
UPDATE tools SET skill_id = (SELECT skill_id FROM skills WHERE name='file-ops')
  WHERE handler LIKE 'file.%';
UPDATE tools SET skill_id = (SELECT skill_id FROM skills WHERE name='process-exec')
  WHERE handler LIKE 'proc.%';
UPDATE tools SET skill_id = (SELECT skill_id FROM skills WHERE name='git-workflow')
  WHERE handler LIKE 'git.%';
UPDATE tools SET skill_id = (SELECT skill_id FROM skills WHERE name='web-fetch')
  WHERE handler LIKE 'net.%';
