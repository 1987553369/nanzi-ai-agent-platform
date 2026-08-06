# Personal Skill Publication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Execute this plan task-by-task with TDD and review each checkpoint before continuing.

**Goal:** Add a permissioned personal-skill submission and administrator-review flow that publishes an immutable, independently identified platform skill while preserving the personal source skill.

**Architecture:** Keep personal skill files under the existing per-user workspace. Persist publication lineage, review state, hashes, and version metadata in two SQLAlchemy tables; persist immutable submitted snapshots beside the configured skills root; materialize only approved snapshots into a uniquely identified directory under `settings.SKILLS_DIR`. Expose personal submission/status APIs and admin review APIs, then add status/review UI without changing existing personal editing or runtime scope semantics.

**Tech Stack:** FastAPI, SQLAlchemy async ORM, MySQL/PostgreSQL SQL migrations, Pydantic, Vue 3/TypeScript, pytest contract tests.

---

## Scope and execution rules

- Preserve the unrelated dirty files already present in the worktree: `frontend/src/composables/chat/useWorkspaceCanvas.ts`, `frontend/src/views/AgentDebug.vue`, `frontend/src/views/EmbedChat.vue`, `tests/CHECKLIST.md`, the two canvas frontend tests, and their canvas spec/plan.
- Do not run `./dev.sh` or any service build/start script; repository instructions require the user to do that manually.
- Do not stage or commit implementation files automatically. The design/spec commit already exists; leave implementation changes for user-controlled finalization.
- Use `--confcutdir=tests/frontend` for pure frontend contract tests when the root conftest imports unavailable infrastructure dependencies.
- Run targeted tests first and report unrelated baseline failures separately.

## File map

Create:

- `app/models/skill_publication.py` — SQLAlchemy publication lineage and version records.
- `app/services/skill_publication_service.py` — secure snapshot creation, review transitions, materialization, status enrichment, and recovery helpers.
- `db-prod/V111.1-create-skill-publications.sql` — MySQL schema.
- `db-prod-pg/V10-create-skill-publications.sql` — PostgreSQL schema.
- `tests/services/test_skill_publication_service.py` — no-infrastructure service and filesystem tests.
- `tests/api/portal/test_skill_publication_routes.py` — route-level permission and state-transition tests.
- `tests/frontend/test_skill_publication_contract.py` — source-contract tests for personal status and admin review UI.

Modify:

- `app/api/portal/endpoints/personal_skills.py` — personal submit/status endpoints and list/detail status enrichment.
- `app/api/portal/endpoints/skills.py` — admin review queue/detail/approve/reject endpoints before dynamic `/{skill_id}` routes.
- `frontend/src/views/SkillsManagement.vue` — personal submit status, review tab, review modal, and platform/source labels.
- `tests/CHECKLIST.md` — add the targeted feature entry only after tests pass.

## Task 1: Add publication persistence and migrations

**Files:**
- Create: `app/models/skill_publication.py`
- Create: `db-prod/V111.1-create-skill-publications.sql`
- Create: `db-prod-pg/V10-create-skill-publications.sql`
- Test: `tests/services/test_skill_publication_service.py`

- [ ] **Step 1: Write model contract tests**

Assert the two model classes expose exact table names and columns: `skill_publications(id, platform_skill_id, source_user_id, source_personal_skill_id, name, description, current_version, status, created_at, updated_at, revoked_at, revoked_by)` and `skill_publication_versions(id, publication_id, version_number, status, snapshot_path, content_sha256, file_count, total_size, submitted_by, submitted_at, reviewed_by, reviewed_at, review_comment, published_at, materialized_path)`.

- [ ] **Step 2: Run tests to verify failure**

Run `venv/bin/python -m pytest tests/services/test_skill_publication_service.py -q`. Expected: collection or assertion failure because the model/test fixtures do not exist.

- [ ] **Step 3: Implement models**

Use `app.core.orm.Base`, `String(36)` UUID IDs, `String(32)` states, `Text` for descriptions/comments/paths, `Integer` for versions/counts, `BigInteger` for `total_size`, and `DateTime(default=datetime.now)`. Add `SkillPublication.versions` with `cascade="all, delete-orphan"`, uniqueness on `platform_skill_id` and `(publication_id, version_number)`, and indexes on state/source/publication IDs.

- [ ] **Step 4: Add paired migrations**

Create matching MySQL `V110` and PostgreSQL `V10` tables with the same columns, foreign-key cascade, unique constraints, and indexes. Use MySQL `BIGINT`/`DATETIME` and PostgreSQL `BIGINT`/`TIMESTAMP`; do not add a new permission row because review reuses `menu:skills_management`.

- [ ] **Step 5: Run model/static checks**

Run `venv/bin/python -m pytest tests/services/test_skill_publication_service.py -q` and `git diff --check`. Expected: model tests pass and no whitespace errors. Do not claim database execution without a real database.

## Task 2: Implement secure snapshot and publication service

**Files:**
- Create: `app/services/skill_publication_service.py`
- Test: `tests/services/test_skill_publication_service.py`

- [ ] **Step 1: Write failing filesystem tests**

Cover: snapshot isolation after personal edits; rejection of symlinks, dotfiles, missing `SKILL.md`, and files/trees over 20 MB; approval materializes a unique global ID while retaining the personal source; failed v2 materialization leaves active v1 unchanged; duplicate pending content returns the existing version.

- [ ] **Step 2: Run tests to verify failure**

Run `venv/bin/python -m pytest tests/services/test_skill_publication_service.py -q`. Expected: missing-service/model failures.

- [ ] **Step 3: Add bounded storage/validation helpers**

Implement these signatures:

```python
def publication_snapshot_root() -> str: ...
def create_personal_skill_snapshot(*, user: dict, skill_id: str) -> SnapshotInfo: ...
def validate_snapshot_tree(root: str) -> SnapshotStats: ...
def materialize_snapshot(*, snapshot_path: str, platform_skill_id: str, version_number: int) -> MaterializeResult: ...
```

Resolve the source with existing `get_user_personal_skills_dir(user)`. Store snapshots in a sibling of `settings.SKILLS_DIR`, mode `0700`, under `<publication_id>/v<version_number>`. Walk with `os.scandir`, reject symlinks/dotfiles/traversal, require `SKILL.md`, cap each file and the tree at 20 MB, compute SHA-256 over sorted relative paths plus bytes, copy to a unique temp directory, then rename into place.

- [ ] **Step 4: Add state-transition helpers**

Implement async functions:

```python
async def submit_personal_skill(session, *, user, skill_id) -> dict: ...
async def list_my_publications(session, *, user_id) -> list[dict]: ...
async def list_pending_publications(session) -> list[dict]: ...
async def get_publication_version(session, *, version_id, include_snapshot: bool) -> dict: ...
async def approve_publication(session, *, version_id, reviewer) -> dict: ...
async def reject_publication(session, *, version_id, reviewer, comment: str) -> dict: ...
```

Generate a stable platform ID on first approval from a sanitized display slug plus an 8-character UUID suffix; reuse it for later versions. Reject a second pending version and duplicate pending hash. Reload/lock before approval or rejection and return conflict for non-pending versions. Materialize to a temporary sibling, verify `SKILL.md`/hash, atomically replace the active directory with a backup, update records, and restore the backup if persistence fails.

- [ ] **Step 5: Run service tests to green**

Run `venv/bin/python -m pytest tests/services/test_skill_publication_service.py -q`. Expected: all snapshot, isolation, duplicate, version, and recovery tests pass.

## Task 3: Add personal submission/status API

**Files:**
- Modify: `app/api/portal/endpoints/personal_skills.py`
- Test: `tests/api/portal/test_skill_publication_routes.py`

- [ ] **Step 1: Write failing route tests**

Cover successful submission with source retention, cross-user denial, list status enrichment, and duplicate pending submission. Use the existing dependency override style from `tests/test_personal_skills_routes.py`; fake the DB session and personal root instead of requiring MySQL/Redis.

- [ ] **Step 2: Run tests to verify failure**

Run `venv/bin/python -m pytest tests/api/portal/test_skill_publication_routes.py -q`. Expected: missing route or missing-field failures.

- [ ] **Step 3: Add the personal submit endpoint**

Add `POST /{skill_id}/publication-requests` before `/{skill_id}`. It uses only `require_api_key`, calls `submit_personal_skill`, maps validation/not-found/conflict to 400/404/409, and returns `{ "status": "success", "data": ... }`.

- [ ] **Step 4: Enrich personal list/detail responses**

Batch-load summaries by current user and source skill IDs. Append `publication_id`, `publication_status`, `current_public_version`, `pending_version`, and `last_review_comment`; an absent DB row maps to `UNPUBLISHED`. Do not change existing file-tree fields or personal permissions.

- [ ] **Step 5: Run the route slice**

Run `venv/bin/python -m pytest tests/api/portal/test_skill_publication_routes.py tests/test_personal_skills_routes.py -q`. Expected: all targeted and existing personal route tests pass.

## Task 4: Add administrator review API

**Files:**
- Modify: `app/api/portal/endpoints/skills.py`
- Test: `tests/api/portal/test_skill_publication_routes.py`

- [ ] **Step 1: Write failing permission/state tests**

Cover non-manager denial, queue listing, approve/publish, reject-with-reason, repeated-review conflict, and preservation of the personal source.

- [ ] **Step 2: Run tests to verify failure**

Run `venv/bin/python -m pytest tests/api/portal/test_skill_publication_routes.py -q`. Expected: missing route/permission failures.

- [ ] **Step 3: Add review routes before `/{skill_id}`**

Add `GET /publication-requests`, `GET /publication-requests/{version_id}`, `POST /publication-requests/{version_id}/approve`, and `POST /publication-requests/{version_id}/reject`. Each uses `require_permission("menu", "menu:skills_management")`; reject accepts `{ "comment": str }` and rejects blank comments; unknown versions return 404 and non-pending versions 409.

- [ ] **Step 4: Return review-safe details**

Return metadata, file tree, hash, size, version, submitter, state, and review comment from the stored snapshot. Never return personal absolute paths, credentials, or files outside the snapshot root.

- [ ] **Step 5: Run the API slice**

Run `venv/bin/python -m pytest tests/api/portal/test_skill_publication_routes.py -q`. Expected: all permission and transition tests pass.

## Task 5: Preserve runtime identity and scope semantics

**Files:**
- Modify: `app/services/ai/skill_resolver.py`
- Modify: `app/services/ai/runtime/agentscope/workspace.py` only if published frontmatter needs explicit enabled filtering
- Test: `tests/ai/test_skill_resolver.py`

- [ ] **Step 1: Write failing resolver tests**

Assert that personal and approved platform skills with the same display name but different IDs are both discoverable, `skills_custom` filters only the platform ID, and `load_skill_md_content(..., scope="global")` cannot read the personal source.

- [ ] **Step 2: Run tests to verify failure**

Run `venv/bin/python -m pytest tests/ai/test_skill_resolver.py -q`. Expected: only the new identity/scope assertions fail.

- [ ] **Step 3: Implement the minimal adjustment**

Keep personal-over-global behavior for actual ID collisions. Rely on the service-generated distinct platform ID. Preserve `scope="global"`/`scope="personal"`, `skills_custom` allowlist behavior, and explicit mounted metadata; only carry publication/version metadata through platform frontmatter when present.

- [ ] **Step 4: Run resolver regressions**

Run `venv/bin/python -m pytest tests/ai/test_skill_resolver.py tests/ai/test_skill_resolver_personal_preload.py tests/services/ai/test_skill_explicit_bindings.py -q`. Expected: all pass; this is not deployment proof.

## Task 6: Add personal and administrator review UI

**Files:**
- Modify: `frontend/src/views/SkillsManagement.vue`
- Create: `tests/frontend/test_skill_publication_contract.py`

- [ ] **Step 1: Write failing frontend contracts**

Assert personal submission URL, visible `UNPUBLISHED/PENDING/PUBLISHED/REJECTED` states, “提交为平台技能/提交新版本”, an admin-only “发布审核” tab, approve/reject URLs, and same-name personal/platform scope/version/source labels.

- [ ] **Step 2: Run tests to verify failure**

Run `venv/bin/python -m pytest --confcutdir=tests/frontend tests/frontend/test_skill_publication_contract.py -q`. Expected: failures for missing strings/API contracts.

- [ ] **Step 3: Extend the skill interface/list mapping**

Add optional `publication_id`, `publication_status`, `current_public_version`, `pending_version`, `last_review_comment`, `platform_skill_id`, and `source_user_name`. Keep personal list loading independent of admin permission.

- [ ] **Step 4: Add personal submit/status UI**

Show scope and publication state on personal cards. Submit to the personal endpoint, refresh list/detail, and leave the editor/current mount untouched on failure. Show rejection comments and “提交新版本” after a published personal skill is edited.

- [ ] **Step 5: Add administrator review UI**

Only in the non-personal-only workbench, load the queue, show candidate metadata/file tree/preview, and provide approve/reject actions. Reject requires a non-empty comment. Refresh queue and platform skills after either action.

- [ ] **Step 6: Run frontend contracts/type checks**

Run `venv/bin/python -m pytest --confcutdir=tests/frontend tests/frontend/test_skill_publication_contract.py tests/frontend/test_personal_skills_experience_contract.py -q`. If the checkout’s existing `vue-tsc --noEmit` command is available, run it; otherwise report it as unrun.

## Task 7: Update checklist and complete targeted verification

**Files:**
- Modify: `tests/CHECKLIST.md`
- Test: all focused files from Tasks 1–6

- [ ] **Step 1: Run combined focused suites**

```bash
venv/bin/python -m pytest tests/services/test_skill_publication_service.py tests/api/portal/test_skill_publication_routes.py tests/ai/test_skill_resolver.py tests/ai/test_skill_resolver_personal_preload.py tests/services/ai/test_skill_explicit_bindings.py -q
venv/bin/python -m pytest --confcutdir=tests/frontend tests/frontend/test_skill_publication_contract.py tests/frontend/test_personal_skills_experience_contract.py -q
git diff --check
```

Expected: targeted tests pass; unrelated broad-suite failures are reported separately.

- [ ] **Step 2: Update `tests/CHECKLIST.md`**

Add one row covering personal submission, admin review, snapshot isolation, unique platform ID, both migrations, backend tests, and frontend contracts. Do not mark real database/authenticated-browser acceptance unless actually run.

- [ ] **Step 3: Inspect final scope**

```bash
git status --short
git diff --stat
git diff --check
```

Confirm only publication implementation files and the checklist changed in addition to the pre-existing unrelated worktree edits. Leave staging, commit, push, and service startup to the user.

## Self-review against the design

- Personal source retention: Tasks 2–3 and route tests.
- Independent platform identity: Tasks 2 and 5.
- Review lifecycle and v1/v2 recovery: Tasks 2 and 4.
- UI closure: Task 6.
- Ownership, path/symlink/dotfile/size checks and permission gating: Tasks 2–4.
- MySQL/PostgreSQL portability: Task 1.
- Explicit non-goals: no automatic replacement, marketplace, external sharing, multi-person approval, or service startup.
