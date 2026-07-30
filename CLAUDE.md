# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## The WAT Architecture

You're working inside the "WAT framework" (Workflows, Agents, Tools). This architecture separates
concerns so that probabilistic AI handles reasoning while deterministic code handles execution. That
separation is what makes the system reliable: if each step an AI performs directly is ~90% accurate,
five chained steps compound down to ~59% success. Offloading execution to deterministic scripts keeps
the AI focused on orchestration and decision-making, where it's strong.

**Layer 1 — Workflows (the instructions)**
Markdown SOPs stored in `workflows/`. Each workflow defines the objective, required inputs, which
tools to use, expected outputs, and how to handle edge cases. Write them in plain language, the way
you'd brief a teammate.

**Layer 2 — Agent (the decision-maker)**
This is Claude's role in this repo: intelligent coordination, not direct execution. Read the relevant
workflow, run tools in the correct sequence, handle failures gracefully, and ask clarifying questions
when needed. Connect intent to execution without trying to do everything yourself.

Example: to pull data from a website, don't scrape it directly — read `workflows/scrape_website.md`,
determine the required inputs, then execute `tools/scrape_single_site.py`.

**Layer 3 — Tools (the execution)**
Python scripts in `tools/` that do the actual work: API calls, data transformations, file operations,
database queries. Credentials and API keys live in `.env`, never in the scripts themselves. These
scripts should be consistent, testable, and fast.

## How to operate

1. **Look for existing tools first.** Before building anything new, check `tools/` for something that
   already covers the task. Only write a new script when nothing existing fits.
2. **Learn and adapt when things fail.**
   - Read the full error message and traceback.
   - Fix the script and retest — but if the script uses paid API calls or credits, check with the user
     before re-running it.
   - Document what you learned in the workflow (rate limits, timing quirks, unexpected behavior).
   - Example: hitting a rate limit leads to digging into the docs, finding a batch endpoint, refactoring
     the tool to use it, verifying it works, and updating the workflow so this doesn't recur.
3. **Keep workflows current.** Update workflows as you learn better methods, discover constraints, or
   hit recurring issues. Don't create or overwrite a workflow file without asking first, unless
   explicitly told to — these are the user's instructions and should be preserved and refined, not
   tossed after one use.

## The self-improvement loop

Every failure is a chance to strengthen the system:
1. Identify what broke.
2. Fix the tool.
3. Verify the fix works.
4. Update the workflow with the new approach.
5. Move on with a more robust system.

## File structure

- **Deliverables**: final outputs belong in cloud services (Google Sheets, Slides, etc.) where the user
  can access them directly — not left as local files.
- **Intermediates**: temporary processing files that can be regenerated on demand.

Directory layout:
- `tmp/` — temporary files (scraped data, intermediate exports). Disposable, regenerated as needed.
- `tools/` — Python scripts for deterministic execution.
- `workflows/` — Markdown SOPs defining what to do and how.
- `.env` — API keys and environment variables. **Never store secrets anywhere else.**
- `credentials.json`, `token.json` — Google OAuth credentials (gitignored).

Core principle: local files are only for processing. Anything the user needs to see or use lives in
cloud services. Everything under `tmp/` is disposable.

## Bottom line

Claude sits between what the user wants (workflows) and what actually gets done (tools). The job is to
read instructions, make smart decisions, call the right tools, recover from errors, and keep improving
the system along the way.
