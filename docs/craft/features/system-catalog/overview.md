# System Catalog (Craft Galleries)

How admin-curated skills, scenarios and report templates reach users.

## 1. Why a separate layer

Before this feature, all three Craft resources were user-owned. Built-in content
existed only as rows an Alembic migration wrote straight into the runtime
tables. That gave no draft state, no categories, no version, and no way for an
admin to change shipped content without a new migration.

The system catalog adds an admin-owned layer in front of the runtime tables.

## 2. Layering

```
Catalog (admin owns)      system_skill / system_scenario / system_report_template
      │                   DRAFT → PUBLISHED → ARCHIVED, version, category, tags
      │
      ├── publish ──────► Runtime projection
      │                   skill / scenario / report_template
      │                   author_user_id IS NULL, system_<kind>_id set
      │                   users read it; every existing consumer is unchanged
      │
      └── fork ─────────► User copy
                          same tables, author_user_id = <user>
                          editable, survives unpublish
```

The catalog is **never read at runtime**. The sandbox skill push, the
`SCENARIO.md` renderer and the report template lookup all keep reading the
runtime tables only.

### Identity rules

| Row | `system_<kind>_id` | `author_user_id` |
|-----|--------------------|------------------|
| Ordinary user resource | NULL | set |
| Catalog projection | set | NULL |
| User fork of a catalog entry | set | set |

`find_projected_skill` and its siblings rely on exactly this: the projection is
the row with the catalog pointer and no owner.

## 3. State flow

| Action | Catalog effect | Runtime effect |
|--------|----------------|----------------|
| Create | row at `DRAFT`, `version = 0` | none |
| Edit | fields change | none — the live projection keeps serving the last published content |
| Publish | `PUBLISHED`, `version += 1`, changelog stored | projection created, or updated in place |
| Unpublish | `ARCHIVED` | projection deleted; **forks untouched** |
| Delete | row removed | forks keep working; their pointer is cleared by `ON DELETE SET NULL` |

Publishing is idempotent by construction: it looks for an existing projection
before creating one, so republishing never produces a second row.

### Guards

- A scenario can only publish when every bound skill is already published, and
  when its report template resolves to a **workspace-owned** row. Binding to a
  user's private template would splice that user's content into every other
  user's `SCENARIO.md`, because the runtime renderer resolves the slug globally.
- A skill cannot be unpublished while a published scenario binds it.
- A report template cannot be unpublished while a scenario references its slug.
  This mirrors `delete_report_template`.
- A published entry cannot be deleted; unpublish first.

## 4. Fork rules

| Kind | What changes in the copy |
|------|--------------------------|
| Skill | Renamed (`docx` → `docx-copy` → `docx-copy-2`). Always bundle-backed: an on-disk built-in is zipped into the file store so the user can edit it. |
| Report template | New slug (`compliance_risk` → `compliance_risk_copy`). A Word asset is **copied**, so the fork owns its bytes. |
| Scenario | Skill bindings still point at the shared projections; forking a pack does not clone every skill. |

Skill renaming is not cosmetic. `uq_user_skill_preference_name` and the sandbox
fileset assembler both reject two enabled skills sharing a name, and the
projection already occupies the entry slug.

A fork records `system_<kind>_version`. When the upstream entry is published
again, that value falls behind and the UI can offer an update.

## 5. Word report templates

A markdown template tells the agent *what sections to write*. A Word template
additionally fixes the *formatting* — letterhead, styles, tables — which is what
finance and regulatory reporting usually requires.

### The contract is the typed placeholder set

Tokens are written `{{name}}` in the document. They are **extracted from the
uploaded file** at upload time, never declared by hand, so the contract shown in
the UI and handed to the agent cannot drift from the real document.

Each name is stored as an object:

```json
{
  "name": "entity_name",
  "kind": "text",
  "required": true,
  "description": "Legal name of the reporting entity",
  "example": "某某股份有限公司"
}
```

Kinds: `text`, `multiline`, `date`, `number`, `table`. A dotted name such as
`findings.title` is a `table` token. A name in the file but missing from the
schema is still a required `text` token (or `table` when dotted).

### Repeating table rows

A table row that contains `{{findings.title}}`, `{{findings.severity}}`, … is a
**prototype row**. The fill JSON supplies an array:

```json
{
  "entity_name": "某某股份有限公司",
  "findings": [
    {
      "title": "银行未达账",
      "severity": "高",
      "amount": "35万",
      "owner": "出纳",
      "source": "工商银行对账单"
    }
  ]
}
```

`fill_template.py` clones that row once per array item. After fill, leftover
`{{…}}` tokens fail the run. Unused JSON keys are reported and are not fatal.

Official Word assets are generated in Python under
`backend/onyx/system_catalog/builtin/word/` so diffs stay reviewable and the
schema cannot drift from the file. Sync attaches the generated bytes. Do not
commit `.docx` binaries.

Extraction joins text at paragraph level across the body, tables, headers and
footers. This matters because Word routinely fragments a token across runs —
`{{total}}` becomes `{{to` + `tal}}` whenever formatting state changes mid-token.
A naive per-run scan misses exactly those tokens.

Uploads are untrusted input, so parsing uses `defusedxml`; a document declaring
XML entities is refused with a 400 rather than expanded.

### Storage and ownership

| Row | Asset |
|-----|-------|
| User template | Owns its blob. Deleting the row deletes the blob. |
| Catalog entry | Owns its blob. |
| Catalog projection | **Borrows** the catalog entry's blob. Unpublishing deletes the row, never the blob. |
| User fork | **Copies** the bytes into its own blob, so editing or deleting a fork cannot disturb the catalog. |

`delete_report_template` checks `system_report_template_id` before removing a
blob, so deleting a projection can never orphan the catalog entry's asset.

### Runtime

When a session's scenario names a Word template, the asset is pushed to
`/workspace/managed/report_templates/<slug>.docx` — a sandbox-root mount, so it
is stable across sessions — and SCENARIO.md carries the fill instructions:

- the exact path to the document,
- the `docx` skill command that fills it (`fill_template.py`, which understands
  run-split tokens),
- the full placeholder list, with an instruction to fill every one rather than
  leave a token bare,
- and an explicit instruction not to fall back to a markdown report.

The push is best-effort: SCENARIO.md is written first, so a push failure
degrades the session to a markdown report instead of failing session setup.

## 6. Shipped content

Built-in content is declared in
[`manifest.py`](../../../../backend/onyx/system_catalog/builtin/manifest.py) —
data, not migrations.

- **Skill entries** point at an on-disk built-in under
  `backend/onyx/skills/builtin/<id>/`, which stays the single home for skill
  content.
- **Report template bodies** live as markdown under
  `backend/onyx/system_catalog/builtin/report_templates/`. Official Word files
  are generated from `backend/onyx/system_catalog/builtin/word/`.
- **Scenarios** keep slug, name, skills, and template pointer in the manifest.
  Playbooks live as YAML under
  `backend/onyx/system_catalog/builtin/scenarios/` and use these keys:
  `domain`, `objective`, `required_inputs`, `phases` (each with `id` and
  `done_when`), `deliverables`, `quality_gates`, `refusal_rules`.
  `render_scenario_markdown_named` writes those keys into `SCENARIO.md` above
  the template block. It does not dump `always_skill_ids`.

`sync_builtin_system_catalog` reconciles the manifest at startup, from
`setup_postgres`. These rules make it safe to run on every boot:

1. **Insert if absent.** Entries are matched by slug.
2. **Refresh unedited BUILTIN rows.** A shipped template or scenario that an
   admin has never published or patched (`published_by_user_id is None` and
   changelog still `Shipped with Onyx.`) is updated when the markdown body,
   playbook, skill list, or official Word schema changes. Republish only when
   content actually changed, so versions do not bump on every boot.
3. **Never overwrite admin work.** A row an admin published or patched is left
   alone.
4. **Adopt before creating.** Rows seeded by earlier releases are linked to their
   catalog entry instead of being shadowed by a duplicate. Skills match on
   `built_in_skill_id`, templates on `slug`, and scenarios on the manifest's
   explicit `adopt_runtime_name`.
5. **Isolate every publish.** Each entry publishes inside its own savepoint. An
   entry that cannot publish — a template slug an end user already holds, or a
   pack whose skills a deployment removed — is logged and skipped. The sync runs
   inside the FastAPI lifespan, so letting one entry raise would be a permanent
   boot failure.

Without rule 2, publishing would add a second `skill` row with the same name and
break the sandbox fileset.

### Adding shipped content

1. For a skill, add the directory under `backend/onyx/skills/builtin/<id>/` and
   register it in `_REGISTRY` in `backend/onyx/skills/built_in.py`.
2. Add the manifest entry. For a report template, also add its body markdown.
3. Restart the API server. The sync publishes the new entry.

No migration is needed.

## 7. API surface

User gallery, read-only plus fork. Requires Craft to be enabled:

```
GET  /api/craft/gallery/{skills|scenarios|report-templates}
GET  /api/craft/gallery/{kind}/{id}
GET  /api/craft/gallery/report-templates/{id}/docx
POST /api/craft/gallery/{kind}/{id}/fork
```

Only `PUBLISHED` entries are reachable. A draft reports as missing rather than
forbidden, so a user cannot probe for unreleased content.

A user's own templates carry the Word asset on the existing route:

```
POST /api/report-templates/{id}/docx    (multipart upload; returns the placeholders)
GET  /api/report-templates/{id}/docx    (download)
```

Admin catalog, requires `FULL_ADMIN_PANEL_ACCESS`:

```
GET    /api/admin/craft/catalog/{kind}
POST   /api/admin/craft/catalog/{kind}
POST   /api/admin/craft/catalog/skills/upload      (multipart bundle)
POST   /api/admin/craft/catalog/report-templates/{id}/docx   (multipart Word asset)
GET    /api/admin/craft/catalog/report-templates/{id}/docx   (download)
GET    /api/admin/craft/catalog/{kind}/{id}
PATCH  /api/admin/craft/catalog/{kind}/{id}
POST   /api/admin/craft/catalog/{kind}/{id}/publish
POST   /api/admin/craft/catalog/{kind}/{id}/unpublish
DELETE /api/admin/craft/catalog/{kind}/{id}
```

The admin router is deliberately not behind the craft-enabled gate: an admin
curating the catalog need not have Craft enabled for their own account. This
matches the existing Craft admin router.

## 8. Frontend

Users reach the galleries through a `Mine / Gallery` tab on the three existing
pages, so no new navigation entry is added:

- `/craft/v1/skills`
- `/craft/v1/scenarios`
- `/craft/v1/report-templates`

Shared pieces live in `web/src/sections/gallery/` and
`web/src/lib/system-catalog/`. `useGalleryTab` holds the tab, category filter,
preview target and fork call so the three pages do not repeat that logic.

Admins manage the catalog at `/admin/craft/catalog`, registered declaratively in
`web/src/lib/admin-routes.ts`.

## 9. Key files

| Purpose | Path |
|---------|------|
| Catalog tables | `backend/onyx/db/models.py` (`SystemSkill`, `SystemScenario`, `SystemReportTemplate`) |
| Validation, search helpers | `backend/onyx/db/system_catalog/constants.py` |
| Publish and unpublish | `backend/onyx/db/system_catalog/publish.py` |
| Fork | `backend/onyx/db/system_catalog/fork.py` |
| Shipped inventory | `backend/onyx/system_catalog/builtin/manifest.py` |
| Startup reconcile | `backend/onyx/system_catalog/builtin/sync.py` |
| User gallery API | `backend/onyx/server/features/system_catalog/gallery_api.py` |
| Admin catalog API | `backend/onyx/server/features/system_catalog/admin_api.py` |
| Schema migration | `backend/alembic/versions/c7d8e9f0a1b2_system_catalog.py` |
| Word template parsing | `backend/onyx/report_templates/docx_template.py` |
| Word asset sandbox push | `backend/onyx/report_templates/sandbox_assets.py` |
| Word template migration | `backend/alembic/versions/d8e9f0a1b2c3_word_report_templates.py` |

## 10. Tests

| File | Covers |
|------|--------|
| `backend/tests/external_dependency_unit/craft/test_system_catalog_lifecycle.py` | draft invisibility, publish/republish, unpublish keeping forks, fork renaming, version drift, reference guards, private-template binding rejected |
| `backend/tests/external_dependency_unit/craft/test_system_catalog_sync.py` | manifest integrity, sync idempotency, legacy adoption, admin edits preserved, a squatted slug does not abort startup |
| `backend/tests/external_dependency_unit/craft/test_system_catalog_api.py` | gallery hides drafts, fork endpoint, admin publish and delete rules |
| `web/src/lib/system-catalog/types.test.ts` | filtering, category collection, version drift, colour and message-key maps |
| `web/src/views/ReportTemplatesGallery.test.tsx` | tab switch, lazy gallery fetch, fork success and failure |
| `backend/tests/external_dependency_unit/craft/test_word_report_templates.py` | placeholder extraction (incl. run-split tokens and entity refusal), asset attach/replace, projection sharing, fork copying, SCENARIO.md fill instructions |
