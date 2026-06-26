from datetime import UTC, datetime
from typing import Optional

from conversational.playbook_draft_models import ALLOWED_PLAYBOOK_DRAFT_STATUSES, PlaybookDraft


class PlaybookDraftStore:
    def __init__(self) -> None:
        self._drafts: dict[str, PlaybookDraft] = {}

    def _key(self, tenant_id: str, workflow_id: str, draft_id: str) -> str:
        return f"{tenant_id}:{workflow_id}:{draft_id}"

    def save(self, draft: PlaybookDraft) -> PlaybookDraft:
        key = self._key(tenant_id=draft.tenant_id, workflow_id=draft.workflow_id, draft_id=draft.draft_id)
        self._drafts[key] = draft
        return draft

    def get(self, tenant_id: str, workflow_id: str, draft_id: str) -> Optional[PlaybookDraft]:
        return self._drafts.get(self._key(tenant_id=tenant_id, workflow_id=workflow_id, draft_id=draft_id))

    def latest(self, tenant_id: str, workflow_id: str) -> Optional[PlaybookDraft]:
        matches = [
            draft for draft in self._drafts.values()
            if draft.tenant_id == tenant_id and draft.workflow_id == workflow_id
        ]
        if not matches:
            return None
        matches.sort(key=lambda draft: draft.created_at, reverse=True)
        return matches[0]

    def list_by_tenant(self, tenant_id: str) -> list[PlaybookDraft]:
        return [draft for draft in self._drafts.values() if draft.tenant_id == tenant_id]

    def update_status(self, tenant_id: str, workflow_id: str, draft_id: str, status: str) -> PlaybookDraft:
        if status not in ALLOWED_PLAYBOOK_DRAFT_STATUSES:
            raise ValueError("Invalid playbook draft status.")

        draft = self.get(tenant_id=tenant_id, workflow_id=workflow_id, draft_id=draft_id)
        if draft is None:
            raise ValueError("Playbook draft not found.")

        draft.status = status
        draft.updated_at = datetime.now(UTC)
        return draft


playbook_draft_store = PlaybookDraftStore()