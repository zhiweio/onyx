# Env Vars & Secrets

## Objective

Give Craft users GitHub-Actions-style environment variables and secrets at
two scopes — personal and Craft project — that scheduled tasks consume
through explicit per-task grants.

A user creates a variable or secret in `/craft/v1/env-vars`, writes
`{{env.NAME}}` / `{{secrets.NAME}}` in a task prompt, and checks the rows
the task may use. At run time only the checked rows are substituted into
the prompt handed to the sandbox agent.

## Semantics (GitHub Actions / GitLab CI mapping)

| Concern | Behavior here | Precedent |
| --- | --- | --- |
| Scopes | `USER` (owner-only) and `PROJECT` (Craft project) | repo / org / environment secrets |
| Grant | `scheduled_task_env_var` rows — a task uses nothing it did not check | reusable workflows must be passed secrets explicitly |
| Secrets | Write-only: value never returned by any API; update = overwrite | GitHub secrets API |
| Masking | Granted secret values replaced with `***` in persisted events, summaries and error details | GitHub log masking |
| Constraints | Name `^[A-Za-z_][A-Za-z0-9_]*$`, reserved prefixes `ONYX_` / `OPENCODE_` / `SANDBOX_` / `GH_` / `GITHUB_`; secret values ≥8 chars, single line | GitHub name rules, GitLab masked-variable rules |
| Revocation | Deleting a var cascades away every task grant; moving a task between projects prunes old-project grants | deleting a secret breaks referencing workflows |

## Permission model

- `USER` rows: creator manages, creator's tasks grant.
- `PROJECT` rows: manage (create / rename / overwrite / delete) requires
  project write access — owner or group manager / curator
  (`user_can_write_project`); listing names and granting requires read
  access (`user_can_read_project`).
- A task may only grant rows from its owner's `USER` scope plus its own
  `project_id`. Selecting the same name from both scopes is rejected — no
  silent precedence.
- The executor re-validates every grant at run time (owner still matches,
  project still matches). A prompt reference that resolves to nothing fails
  the run with `error_class=env_var_resolution_failed` before the sandbox
  is invoked.

## Run-time flow

1. Executor loads the task's grants and decrypts values
   (`resolve_env_vars_for_task_run`).
2. `render_prompt_with_env_vars` substitutes `{{env.X}}` / `{{secrets.X}}`
   into the effective prompt. Turn 0 persists the TEMPLATE — secret
   plaintext never enters the stored transcript.
3. `SecretMasker` walks every sandbox event before persistence, so agent
   output, tool-call text, summaries and error details all carry `***`
   instead of a granted secret's value.

## Storage

- `env_var` table: `name`, `is_secret`, `scope`, `user_id` (creator),
  `project_id`, `value` as `EncryptedString` (`SensitiveValue[str]`).
  Both secrets and plain values are encrypted at rest; `is_secret` only
  controls API readability.
- Uniqueness: partial unique indexes `(user_id, name)` for USER scope and
  `(project_id, name)` for PROJECT scope, enforced by a
  `ck_env_var_scope_project` check constraint pairing.
