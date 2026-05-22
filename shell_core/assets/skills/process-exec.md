---
name: process-exec
description: Run commands and inspect processes in the working directory.
category: workflow
common: 0
trigger_keywords: run, execute, command, build, test, compile, npm, make
trigger_use_when: running a build, test, or other command in the working dir
---
# process-exec

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
