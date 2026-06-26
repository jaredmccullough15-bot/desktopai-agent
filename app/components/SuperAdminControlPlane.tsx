"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type SuperAdminUser = {
  id: string;
  name: string;
  email: string;
  role: "super_admin";
};

type TenantRecord = {
  tenant_id: string;
  name: string;
  status: "active" | "suspended" | string;
  contact_email?: string | null;
  notes?: string | null;
  settings?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

type TenantUser = {
  id: string;
  tenant_id?: string | null;
  name: string;
  email: string;
  role: string;
  status: string;
  last_login_at?: string | null;
};

type TenantKnowledge = {
  knowledge_id: string;
  tenant_id?: string | null;
  title: string;
  category: string;
  content: string;
  tags: string[];
  applies_to: string[];
  status: "active" | "draft" | "archived";
  copied_from_tenant_id?: string | null;
  copied_from_record_id?: string | null;
};

type TenantWorkflowSummary = {
  workflow_id: string;
  workflow_name: string;
  enabled: boolean;
  version?: string;
};

type TenantWorkflowResponse = {
  tenant_id: string;
  workflows: TenantWorkflowSummary[];
};

type IntegrationCredential = {
  integration_id: string;
  tenant_id: string;
  integration_type: string;
  name: string;
  status: string;
  settings: Record<string, unknown>;
  secret_masked: string;
  created_at: string;
  updated_at: string;
};

type TemplateBundle = {
  bundle_id: string;
  name: string;
  description?: string | null;
  templates: Array<{
    source_tenant_id: string;
    workflow_id: string;
    activate: boolean;
  }>;
  created_at?: string;
  updated_at?: string;
};

type TenantWorkersResponse = {
  tenant_id: string;
  workers: Array<{
    machine_uuid: string;
    machine_name?: string;
    tenant_id?: string | null;
    status?: string;
    worker_version?: string | null;
    execution_mode?: string | null;
    last_seen?: string | null;
  }>;
};

type AuditLog = {
  id: number;
  event_type: string;
  actor_user_name?: string | null;
  actor_role?: string | null;
  tenant_id?: string | null;
  target_type?: string | null;
  target_id?: string | null;
  status_code?: number | null;
  details?: Record<string, unknown>;
  created_at: string;
};

type ApiFetch = (url: string, init?: RequestInit & { allowUnauthorized?: boolean }) => Promise<Response>;

type Props = {
  apiBase: string;
  currentUser: SuperAdminUser;
  apiFetch: ApiFetch;
};

type PanelTab = "users" | "knowledge" | "workflows" | "integrations" | "bundles" | "workers" | "audit";

const PANEL_TABS: Array<{ key: PanelTab; label: string }> = [
  { key: "users", label: "Tenant Users" },
  { key: "knowledge", label: "Tenant Knowledge" },
  { key: "workflows", label: "Tenant Workflows" },
  { key: "integrations", label: "Tenant Integrations" },
  { key: "bundles", label: "Template Bundles" },
  { key: "workers", label: "Tenant Workers" },
  { key: "audit", label: "Tenant Audit Logs" },
];

const BUTTON_PRIMARY =
  "rounded-lg bg-amber-400 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-60";
const BUTTON_SECONDARY =
  "rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 transition hover:border-amber-300/60 hover:text-amber-100 disabled:cursor-not-allowed disabled:opacity-60";
const INPUT_BASE =
  "w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100 outline-none focus:border-amber-300/60";

function fmtTime(value?: string | null): string {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

async function readError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    const detail = payload?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail)) return detail.map((item) => String(item)).join(", ");
    return `Request failed (${response.status})`;
  } catch {
    return `Request failed (${response.status})`;
  }
}

export function SuperAdminControlPlane({ apiBase, currentUser, apiFetch }: Props) {
  const [loadingPlatform, setLoadingPlatform] = useState(false);
  const [platformError, setPlatformError] = useState<string | null>(null);
  const [platformNotice, setPlatformNotice] = useState<string | null>(null);

  const [tenants, setTenants] = useState<TenantRecord[]>([]);
  const [tenantSearch, setTenantSearch] = useState("");
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null);

  const [createTenantName, setCreateTenantName] = useState("");
  const [createTenantId, setCreateTenantId] = useState("");
  const [createTenantEmail, setCreateTenantEmail] = useState("");
  const [creatingTenant, setCreatingTenant] = useState(false);

  const [activePanelTab, setActivePanelTab] = useState<PanelTab>("users");
  const [tenantPanelBusy, setTenantPanelBusy] = useState(false);
  const [tenantPanelError, setTenantPanelError] = useState<string | null>(null);

  const [tenantUsers, setTenantUsers] = useState<TenantUser[]>([]);
  const [newUserName, setNewUserName] = useState("");
  const [newUserEmail, setNewUserEmail] = useState("");
  const [newUserPassword, setNewUserPassword] = useState("");
  const [newUserRole, setNewUserRole] = useState("viewer");

  const [tenantKnowledge, setTenantKnowledge] = useState<TenantKnowledge[]>([]);
  const [knowledgeDrafts, setKnowledgeDrafts] = useState<Record<string, { title: string; category: string; content: string; status: string }>>({});
  const [newKnowledgeTitle, setNewKnowledgeTitle] = useState("");
  const [newKnowledgeCategory, setNewKnowledgeCategory] = useState("reference");
  const [newKnowledgeContent, setNewKnowledgeContent] = useState("");
  const [knowledgeCopySourceTenant, setKnowledgeCopySourceTenant] = useState("");
  const [knowledgeCopySourceId, setKnowledgeCopySourceId] = useState("");

  const [tenantWorkflows, setTenantWorkflows] = useState<TenantWorkflowSummary[]>([]);
  const [workflowCopySourceTenant, setWorkflowCopySourceTenant] = useState("");
  const [workflowCopySourceId, setWorkflowCopySourceId] = useState("");

  const [tenantWorkers, setTenantWorkers] = useState<TenantWorkersResponse["workers"]>([]);

  const [tenantIntegrations, setTenantIntegrations] = useState<IntegrationCredential[]>([]);
  const [newIntegrationType, setNewIntegrationType] = useState("crm");
  const [newIntegrationName, setNewIntegrationName] = useState("");
  const [newIntegrationSecret, setNewIntegrationSecret] = useState("");
  const [newIntegrationBaseUrl, setNewIntegrationBaseUrl] = useState("");
  const [editingIntegrationId, setEditingIntegrationId] = useState<string | null>(null);
  const [editIntegrationName, setEditIntegrationName] = useState("");
  const [editIntegrationStatus, setEditIntegrationStatus] = useState("active");
  const [editIntegrationSecret, setEditIntegrationSecret] = useState("");

  const [bundles, setBundles] = useState<TemplateBundle[]>([]);
  const [newBundleId, setNewBundleId] = useState("");
  const [newBundleName, setNewBundleName] = useState("");
  const [newBundleSourceTenant, setNewBundleSourceTenant] = useState("");
  const [newBundleWorkflowId, setNewBundleWorkflowId] = useState("");
  const [bundleApplyId, setBundleApplyId] = useState("");
  const [bundleResult, setBundleResult] = useState<string | null>(null);

  const [tenantAudit, setTenantAudit] = useState<AuditLog[]>([]);

  const selectedTenant = useMemo(
    () => tenants.find((tenant) => tenant.tenant_id === selectedTenantId) ?? null,
    [tenants, selectedTenantId],
  );

  const filteredTenants = useMemo(() => {
    const needle = tenantSearch.trim().toLowerCase();
    if (!needle) return tenants;
    return tenants.filter((tenant) => {
      return (
        tenant.tenant_id.toLowerCase().includes(needle)
        || tenant.name.toLowerCase().includes(needle)
        || String(tenant.contact_email || "").toLowerCase().includes(needle)
      );
    });
  }, [tenantSearch, tenants]);

  const withPlatformErrorHandling = useCallback(async (response: Response) => {
    if (response.status === 403) {
      throw new Error("Insufficient permission for super-admin action.");
    }
    if (response.status === 404) {
      throw new Error("Tenant or entity not found.");
    }
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    return response;
  }, []);

  const loadTenants = useCallback(async () => {
    setLoadingPlatform(true);
    setPlatformError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/tenants`);
      await withPlatformErrorHandling(response);
      const payload = (await response.json()) as TenantRecord[];
      const records = Array.isArray(payload) ? payload : [];
      setTenants(records);
      if (!selectedTenantId && records.length > 0) {
        setSelectedTenantId(records[0].tenant_id);
      }
    } catch (error) {
      setPlatformError(error instanceof Error ? error.message : "Failed to load tenants");
    } finally {
      setLoadingPlatform(false);
    }
  }, [apiBase, apiFetch, selectedTenantId, withPlatformErrorHandling]);

  const loadTenantSuite = useCallback(async (tenantId: string) => {
    setTenantPanelBusy(true);
    setTenantPanelError(null);
    try {
      const [usersRes, knowledgeRes, workflowsRes, integrationsRes, workersRes] = await Promise.all([
        apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(tenantId)}/users?limit=300`),
        apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(tenantId)}/knowledge?limit=500`),
        apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(tenantId)}/workflows`),
        apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(tenantId)}/integration-credentials`),
        apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(tenantId)}/workers`),
      ]);

      await Promise.all([
        withPlatformErrorHandling(usersRes),
        withPlatformErrorHandling(knowledgeRes),
        withPlatformErrorHandling(workflowsRes),
        withPlatformErrorHandling(integrationsRes),
        withPlatformErrorHandling(workersRes),
      ]);

      const users = (await usersRes.json()) as TenantUser[];
      const knowledge = (await knowledgeRes.json()) as TenantKnowledge[];
      const workflowsPayload = (await workflowsRes.json()) as TenantWorkflowResponse;
      const integrations = (await integrationsRes.json()) as IntegrationCredential[];
      const workers = (await workersRes.json()) as TenantWorkersResponse;

      setTenantUsers(Array.isArray(users) ? users : []);
      setTenantKnowledge(Array.isArray(knowledge) ? knowledge : []);
      setTenantWorkflows(Array.isArray(workflowsPayload.workflows) ? workflowsPayload.workflows : []);
      setTenantWorkers(Array.isArray(workers.workers) ? workers.workers : []);
      setTenantIntegrations(Array.isArray(integrations) ? integrations : []);

      setPlatformNotice(
        `Loaded tenant suite for ${tenantId}: ${users.length} users, ${knowledge.length} knowledge entries, ${workflowsPayload.workflows?.length ?? 0} workflows, ${integrations.length} integrations, ${workers.workers?.length ?? 0} workers.`,
      );
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to load tenant suite");
    } finally {
      setTenantPanelBusy(false);
    }
  }, [apiBase, apiFetch, withPlatformErrorHandling]);

  const loadBundles = useCallback(async () => {
    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/template-bundles`);
      await withPlatformErrorHandling(response);
      const payload = (await response.json()) as TemplateBundle[];
      setBundles(Array.isArray(payload) ? payload : []);
    } catch {
      setBundles([]);
    }
  }, [apiBase, apiFetch, withPlatformErrorHandling]);

  const loadAuditForTenant = useCallback(async (tenantId: string) => {
    try {
      const response = await apiFetch(`${apiBase}/api/admin/audit-logs?limit=300`);
      await withPlatformErrorHandling(response);
      const payload = (await response.json()) as AuditLog[];
      const tenantFiltered = (Array.isArray(payload) ? payload : []).filter((entry) => {
        const tenantMatch = String(entry.tenant_id || "").trim() === tenantId;
        const detailsTenant = String((entry.details as { tenant_id?: unknown } | undefined)?.tenant_id || "").trim() === tenantId;
        const sourceTenant = String((entry.details as { source_tenant_id?: unknown } | undefined)?.source_tenant_id || "").trim() === tenantId;
        const targetTenant = String((entry.details as { target_tenant_id?: unknown } | undefined)?.target_tenant_id || "").trim() === tenantId;
        return tenantMatch || detailsTenant || sourceTenant || targetTenant;
      });
      setTenantAudit(tenantFiltered);
    } catch {
      setTenantAudit([]);
    }
  }, [apiBase, apiFetch, withPlatformErrorHandling]);

  useEffect(() => {
    void loadTenants();
    void loadBundles();
  }, [loadBundles, loadTenants]);

  useEffect(() => {
    if (!selectedTenantId) return;
    void loadTenantSuite(selectedTenantId);
    void loadAuditForTenant(selectedTenantId);
  }, [selectedTenantId, loadTenantSuite, loadAuditForTenant]);

  const createTenant = useCallback(async () => {
    if (!createTenantId.trim() || !createTenantName.trim()) {
      setPlatformError("Tenant ID and tenant name are required.");
      return;
    }
    setCreatingTenant(true);
    setPlatformError(null);
    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/tenants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: createTenantId.trim(),
          name: createTenantName.trim(),
          contact_email: createTenantEmail.trim() || null,
        }),
      });
      await withPlatformErrorHandling(response);
      setCreateTenantId("");
      setCreateTenantName("");
      setCreateTenantEmail("");
      await loadTenants();
      setPlatformNotice("Tenant created.");
    } catch (error) {
      setPlatformError(error instanceof Error ? error.message : "Failed to create tenant");
    } finally {
      setCreatingTenant(false);
    }
  }, [apiBase, apiFetch, createTenantEmail, createTenantId, createTenantName, loadTenants, withPlatformErrorHandling]);

  const updateTenantStatus = useCallback(async (tenantId: string, status: "active" | "suspended") => {
    const confirmed = window.confirm(
      status === "suspended"
        ? "Suspend this tenant? This archives access at tenant level without deleting records."
        : "Reactivate this tenant?",
    );
    if (!confirmed) return;

    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(tenantId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status }),
      });
      await withPlatformErrorHandling(response);
      await loadTenants();
      setPlatformNotice(status === "suspended" ? "Tenant suspended." : "Tenant reactivated.");
    } catch (error) {
      setPlatformError(error instanceof Error ? error.message : "Failed to update tenant status");
    }
  }, [apiBase, apiFetch, loadTenants, withPlatformErrorHandling]);

  const createTenantUser = useCallback(async () => {
    if (!selectedTenantId) return;
    if (!newUserName.trim() || !newUserEmail.trim() || !newUserPassword.trim()) {
      setTenantPanelError("Name, email, and password are required.");
      return;
    }
    try {
      const response = await apiFetch(`${apiBase}/api/admin/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newUserName.trim(),
          email: newUserEmail.trim(),
          password: newUserPassword,
          role: newUserRole,
          status: "active",
          tenant_id: selectedTenantId,
        }),
      });
      await withPlatformErrorHandling(response);
      setNewUserName("");
      setNewUserEmail("");
      setNewUserPassword("");
      setNewUserRole("viewer");
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Tenant user created.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to create tenant user");
    }
  }, [apiBase, apiFetch, loadTenantSuite, newUserEmail, newUserName, newUserPassword, newUserRole, selectedTenantId, withPlatformErrorHandling]);

  const toggleTenantUserStatus = useCallback(async (user: TenantUser) => {
    if (!selectedTenantId) return;
    const nextStatus = String(user.status || "").toLowerCase() === "active" ? "inactive" : "active";
    const confirmed = window.confirm(nextStatus === "inactive" ? "Archive/disable this user?" : "Reactivate this user?");
    if (!confirmed) return;

    try {
      const response = await apiFetch(`${apiBase}/api/admin/users/${encodeURIComponent(user.id)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      await withPlatformErrorHandling(response);
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice(nextStatus === "inactive" ? "User archived/disabled." : "User reactivated.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to update user status");
    }
  }, [apiBase, apiFetch, loadTenantSuite, selectedTenantId, withPlatformErrorHandling]);

  const createKnowledge = useCallback(async () => {
    if (!selectedTenantId) return;
    if (!newKnowledgeTitle.trim() || !newKnowledgeCategory.trim() || !newKnowledgeContent.trim()) {
      setTenantPanelError("Knowledge title, category, and content are required.");
      return;
    }

    try {
      const response = await apiFetch(`${apiBase}/api/knowledge`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: newKnowledgeTitle.trim(),
          category: newKnowledgeCategory.trim(),
          applies_to: [],
          content: newKnowledgeContent,
          source_type: "manual",
          tags: [],
          status: "draft",
          tenant_id: selectedTenantId,
        }),
      });
      await withPlatformErrorHandling(response);
      setNewKnowledgeTitle("");
      setNewKnowledgeCategory("reference");
      setNewKnowledgeContent("");
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Knowledge created as draft.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to create knowledge");
    }
  }, [apiBase, apiFetch, loadTenantSuite, newKnowledgeCategory, newKnowledgeContent, newKnowledgeTitle, selectedTenantId, withPlatformErrorHandling]);

  const saveKnowledgeDraft = useCallback(async (knowledgeId: string) => {
    if (!selectedTenantId) return;
    const draft = knowledgeDrafts[knowledgeId];
    if (!draft) return;

    try {
      const response = await apiFetch(`${apiBase}/api/knowledge/${encodeURIComponent(knowledgeId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: draft.title,
          category: draft.category,
          content: draft.content,
          status: draft.status,
        }),
      });
      await withPlatformErrorHandling(response);
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Knowledge saved.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to save knowledge");
    }
  }, [apiBase, apiFetch, knowledgeDrafts, loadTenantSuite, selectedTenantId, withPlatformErrorHandling]);

  const archiveKnowledge = useCallback(async (knowledgeId: string) => {
    if (!selectedTenantId) return;
    const confirmed = window.confirm("Archive this knowledge record?");
    if (!confirmed) return;

    try {
      const response = await apiFetch(`${apiBase}/api/knowledge/${encodeURIComponent(knowledgeId)}/archive`, {
        method: "POST",
      });
      await withPlatformErrorHandling(response);
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Knowledge archived.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to archive knowledge");
    }
  }, [apiBase, apiFetch, loadTenantSuite, selectedTenantId, withPlatformErrorHandling]);

  const copyKnowledge = useCallback(async () => {
    if (!selectedTenantId) return;
    if (!knowledgeCopySourceTenant.trim() || !knowledgeCopySourceId.trim()) {
      setTenantPanelError("Source tenant and source knowledge ID are required.");
      return;
    }

    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/knowledge/copy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_tenant_id: knowledgeCopySourceTenant.trim(),
          source_knowledge_id: knowledgeCopySourceId.trim(),
          target_tenant_id: selectedTenantId,
          activate: false,
        }),
      });
      await withPlatformErrorHandling(response);
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Knowledge copied as draft.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to copy knowledge");
    }
  }, [apiBase, apiFetch, knowledgeCopySourceId, knowledgeCopySourceTenant, loadTenantSuite, selectedTenantId, withPlatformErrorHandling]);

  const copyWorkflow = useCallback(async () => {
    if (!selectedTenantId) return;
    if (!workflowCopySourceTenant.trim() || !workflowCopySourceId.trim()) {
      setTenantPanelError("Source tenant and source workflow ID are required.");
      return;
    }

    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/workflows/copy`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_tenant_id: workflowCopySourceTenant.trim(),
          source_workflow_id: workflowCopySourceId.trim(),
          target_tenant_id: selectedTenantId,
          activate: false,
        }),
      });
      await withPlatformErrorHandling(response);
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Workflow copied as inactive.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to copy workflow");
    }
  }, [apiBase, apiFetch, loadTenantSuite, selectedTenantId, withPlatformErrorHandling, workflowCopySourceId, workflowCopySourceTenant]);

  const createIntegration = useCallback(async () => {
    if (!selectedTenantId) return;
    if (!newIntegrationName.trim() || !newIntegrationSecret.trim()) {
      setTenantPanelError("Integration name and secret are required.");
      return;
    }

    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(selectedTenantId)}/integration-credentials`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          integration_type: newIntegrationType,
          name: newIntegrationName,
          secret: newIntegrationSecret,
          status: "active",
          settings: { base_url: newIntegrationBaseUrl || undefined },
        }),
      });
      await withPlatformErrorHandling(response);
      setNewIntegrationName("");
      setNewIntegrationSecret("");
      setNewIntegrationBaseUrl("");
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Integration secret saved. Secret is now masked.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to create integration");
    }
  }, [apiBase, apiFetch, loadTenantSuite, newIntegrationBaseUrl, newIntegrationName, newIntegrationSecret, newIntegrationType, selectedTenantId, withPlatformErrorHandling]);

  const saveIntegrationUpdate = useCallback(async () => {
    if (!selectedTenantId || !editingIntegrationId) return;
    try {
      const payload: Record<string, unknown> = {
        name: editIntegrationName,
        status: editIntegrationStatus,
      };
      if (editIntegrationSecret.trim()) {
        payload.secret = editIntegrationSecret;
      }

      const response = await apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(selectedTenantId)}/integration-credentials/${encodeURIComponent(editingIntegrationId)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await withPlatformErrorHandling(response);
      setEditingIntegrationId(null);
      setEditIntegrationName("");
      setEditIntegrationStatus("active");
      setEditIntegrationSecret("");
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Integration updated. Secret remains masked.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to update integration");
    }
  }, [apiBase, apiFetch, editIntegrationName, editIntegrationSecret, editIntegrationStatus, editingIntegrationId, loadTenantSuite, selectedTenantId, withPlatformErrorHandling]);

  const archiveIntegration = useCallback(async (integrationId: string) => {
    if (!selectedTenantId) return;
    const confirmed = window.confirm("Archive this integration credential?");
    if (!confirmed) return;

    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(selectedTenantId)}/integration-credentials/${encodeURIComponent(integrationId)}`, {
        method: "DELETE",
      });
      await withPlatformErrorHandling(response);
      await loadTenantSuite(selectedTenantId);
      setPlatformNotice("Integration archived.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to archive integration");
    }
  }, [apiBase, apiFetch, loadTenantSuite, selectedTenantId, withPlatformErrorHandling]);

  const createBundle = useCallback(async () => {
    if (!newBundleName.trim() || !newBundleSourceTenant.trim() || !newBundleWorkflowId.trim()) {
      setTenantPanelError("Bundle name, source tenant, and workflow ID are required.");
      return;
    }

    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/template-bundles`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bundle_id: newBundleId.trim() || undefined,
          name: newBundleName.trim(),
          templates: [{
            source_tenant_id: newBundleSourceTenant.trim(),
            workflow_id: newBundleWorkflowId.trim(),
            activate: false,
          }],
        }),
      });
      await withPlatformErrorHandling(response);
      setNewBundleId("");
      setNewBundleName("");
      setNewBundleSourceTenant("");
      setNewBundleWorkflowId("");
      await loadBundles();
      setPlatformNotice("Template bundle created.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to create bundle");
    }
  }, [apiBase, apiFetch, loadBundles, newBundleId, newBundleName, newBundleSourceTenant, newBundleWorkflowId, withPlatformErrorHandling]);

  const applyBundle = useCallback(async () => {
    if (!selectedTenantId || !bundleApplyId.trim()) {
      setTenantPanelError("Select a bundle before applying.");
      return;
    }

    try {
      const response = await apiFetch(`${apiBase}/api/super-admin/tenants/${encodeURIComponent(selectedTenantId)}/template-bundles/${encodeURIComponent(bundleApplyId.trim())}/apply`, {
        method: "POST",
      });
      await withPlatformErrorHandling(response);
      const payload = (await response.json()) as { copied_count?: number; copied_workflow_ids?: string[] };
      await loadTenantSuite(selectedTenantId);
      const count = Number(payload.copied_count || 0);
      setBundleResult(`Applied bundle: ${count} workflow(s) copied.`);
      setPlatformNotice("Starter bundle applied.");
    } catch (error) {
      setTenantPanelError(error instanceof Error ? error.message : "Failed to apply bundle");
    }
  }, [apiBase, apiFetch, bundleApplyId, loadTenantSuite, selectedTenantId, withPlatformErrorHandling]);

  return (
    <section className="mb-6 rounded-2xl border border-amber-400/30 bg-gradient-to-br from-slate-900/95 via-slate-950/90 to-amber-950/20 p-4 shadow-xl shadow-amber-950/20">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-amber-200">Super Admin Control Plane</p>
          <h2 className="mt-1 text-lg font-semibold text-slate-50">Platform Overview</h2>
          <p className="mt-1 text-sm text-slate-300">Manage tenants and tenant suites. Actions here affect selected tenant data.</p>
        </div>
        <div className="rounded-lg border border-amber-300/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
          Signed in as {currentUser.name} ({currentUser.role})
        </div>
      </div>

      {(platformError || tenantPanelError) && (
        <p className="mt-3 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-100">
          {platformError || tenantPanelError}
        </p>
      )}
      {platformNotice && (
        <p className="mt-3 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
          {platformNotice}
        </p>
      )}

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(300px,0.9fr)_minmax(0,2.1fr)]">
        <aside className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Tenant list</p>
            <button type="button" className={BUTTON_SECONDARY} onClick={() => void loadTenants()} disabled={loadingPlatform}>
              {loadingPlatform ? "Refreshing..." : "Refresh"}
            </button>
          </div>

          <input
            value={tenantSearch}
            onChange={(event) => setTenantSearch(event.target.value)}
            placeholder="Search by tenant id/name"
            className={INPUT_BASE}
          />

          <div className="max-h-72 space-y-2 overflow-auto">
            {filteredTenants.map((tenant) => (
              <div key={tenant.tenant_id} className="rounded-lg border border-slate-800 bg-slate-900/70 p-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-semibold text-slate-100">{tenant.name}</p>
                    <p className="text-xs text-slate-400">{tenant.tenant_id}</p>
                  </div>
                  <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${String(tenant.status).toLowerCase() === "active" ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-200"}`}>
                    {tenant.status}
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  <button type="button" className={BUTTON_SECONDARY} onClick={() => setSelectedTenantId(tenant.tenant_id)}>
                    Open tenant
                  </button>
                  <button
                    type="button"
                    className={BUTTON_SECONDARY}
                    onClick={() => void updateTenantStatus(tenant.tenant_id, String(tenant.status).toLowerCase() === "active" ? "suspended" : "active")}
                  >
                    {String(tenant.status).toLowerCase() === "active" ? "Suspend" : "Reactivate"}
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
            <p className="text-xs uppercase tracking-[0.14em] text-slate-400">Create tenant</p>
            <div className="mt-2 space-y-2">
              <input value={createTenantId} onChange={(event) => setCreateTenantId(event.target.value)} placeholder="Tenant ID" className={INPUT_BASE} />
              <input value={createTenantName} onChange={(event) => setCreateTenantName(event.target.value)} placeholder="Tenant name" className={INPUT_BASE} />
              <input value={createTenantEmail} onChange={(event) => setCreateTenantEmail(event.target.value)} placeholder="Contact email" className={INPUT_BASE} />
              <button type="button" className={BUTTON_PRIMARY} onClick={() => void createTenant()} disabled={creatingTenant}>
                {creatingTenant ? "Creating..." : "Create Tenant"}
              </button>
            </div>
          </div>
        </aside>

        <div className="rounded-xl border border-amber-300/30 bg-slate-950/70 p-3">
          {!selectedTenant ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-4 py-8 text-center text-sm text-slate-400">
              Open a tenant from the left panel to load tenant suite data.
            </div>
          ) : (
            <>
              <div className="rounded-lg border border-amber-400/35 bg-amber-500/10 p-3">
                <p className="text-xs uppercase tracking-[0.14em] text-amber-200">Tenant context</p>
                <p className="mt-1 text-sm font-semibold text-amber-50">Super Admin viewing tenant: {selectedTenant.name}</p>
                <p className="mt-1 text-xs text-amber-100/90">
                  Tenant ID: {selectedTenant.tenant_id} • Status: {selectedTenant.status}. Warning: actions below affect this tenant only.
                </p>
                <div className="mt-2">
                  <button type="button" className={BUTTON_SECONDARY} onClick={() => setSelectedTenantId(null)}>
                    Back to platform dashboard
                  </button>
                </div>
              </div>

              <div className="mt-3 flex flex-wrap gap-2 border-b border-slate-800 pb-3">
                {PANEL_TABS.map((tab) => (
                  <button
                    key={tab.key}
                    type="button"
                    className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition ${activePanelTab === tab.key ? "bg-amber-400 text-slate-950" : "border border-slate-700 bg-slate-900 text-slate-200 hover:border-amber-300/60 hover:text-amber-100"}`}
                    onClick={() => setActivePanelTab(tab.key)}
                  >
                    {tab.label}
                  </button>
                ))}
                <button type="button" className={`${BUTTON_SECONDARY} ml-auto`} onClick={() => void loadTenantSuite(selectedTenant.tenant_id)} disabled={tenantPanelBusy}>
                  {tenantPanelBusy ? "Loading suite..." : "Refresh tenant suite"}
                </button>
              </div>

              {activePanelTab === "users" && (
                <div className="mt-4 space-y-3">
                  <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/70 p-3 md:grid-cols-2">
                    <input value={newUserName} onChange={(event) => setNewUserName(event.target.value)} placeholder="Name" className={INPUT_BASE} />
                    <input value={newUserEmail} onChange={(event) => setNewUserEmail(event.target.value)} placeholder="Email" className={INPUT_BASE} />
                    <input type="password" value={newUserPassword} onChange={(event) => setNewUserPassword(event.target.value)} placeholder="Password" className={INPUT_BASE} />
                    <select value={newUserRole} onChange={(event) => setNewUserRole(event.target.value)} className={INPUT_BASE}>
                      <option value="viewer">viewer</option>
                      <option value="runner">runner</option>
                      <option value="teacher">teacher</option>
                      <option value="admin">admin</option>
                    </select>
                    <button type="button" className={BUTTON_PRIMARY} onClick={() => void createTenantUser()}>
                      Create tenant user
                    </button>
                  </div>

                  <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                    <table className="min-w-full text-left text-xs text-slate-200">
                      <thead className="text-slate-400">
                        <tr>
                          <th className="py-1 pr-2">Name</th>
                          <th className="py-1 pr-2">Email</th>
                          <th className="py-1 pr-2">Role</th>
                          <th className="py-1 pr-2">Status</th>
                          <th className="py-1 pr-2">Last login</th>
                          <th className="py-1">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tenantUsers.map((user) => (
                          <tr key={user.id} className="border-t border-slate-800/70">
                            <td className="py-1 pr-2">{user.name}</td>
                            <td className="py-1 pr-2 text-slate-400">{user.email}</td>
                            <td className="py-1 pr-2">{user.role}</td>
                            <td className="py-1 pr-2">{user.status}</td>
                            <td className="py-1 pr-2 text-slate-400">{fmtTime(user.last_login_at)}</td>
                            <td className="py-1">
                              <button type="button" className={BUTTON_SECONDARY} onClick={() => void toggleTenantUserStatus(user)}>
                                {String(user.status).toLowerCase() === "active" ? "Archive/Disable" : "Reactivate"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activePanelTab === "knowledge" && (
                <div className="mt-4 space-y-3">
                  <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                    <input value={newKnowledgeTitle} onChange={(event) => setNewKnowledgeTitle(event.target.value)} placeholder="Knowledge title" className={INPUT_BASE} />
                    <input value={newKnowledgeCategory} onChange={(event) => setNewKnowledgeCategory(event.target.value)} placeholder="Category" className={INPUT_BASE} />
                    <textarea value={newKnowledgeContent} onChange={(event) => setNewKnowledgeContent(event.target.value)} placeholder="Knowledge content" rows={4} className={`${INPUT_BASE} resize-y`} />
                    <div className="flex flex-wrap gap-2">
                      <button type="button" className={BUTTON_PRIMARY} onClick={() => void createKnowledge()}>Create Draft</button>
                    </div>
                  </div>

                  <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/70 p-3 md:grid-cols-3">
                    <input value={knowledgeCopySourceTenant} onChange={(event) => setKnowledgeCopySourceTenant(event.target.value)} placeholder="Source tenant ID" className={INPUT_BASE} />
                    <input value={knowledgeCopySourceId} onChange={(event) => setKnowledgeCopySourceId(event.target.value)} placeholder="Source knowledge ID" className={INPUT_BASE} />
                    <button type="button" className={BUTTON_SECONDARY} onClick={() => void copyKnowledge()}>
                      Copy Knowledge (as draft)
                    </button>
                  </div>

                  <div className="space-y-2">
                    {tenantKnowledge.map((entry) => {
                      const draft = knowledgeDrafts[entry.knowledge_id] || {
                        title: entry.title,
                        category: entry.category,
                        content: entry.content,
                        status: entry.status,
                      };
                      return (
                        <div key={entry.knowledge_id} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-sm font-semibold text-slate-50">{entry.title}</p>
                            <span className="text-xs text-slate-400">{entry.status}</span>
                          </div>
                          <div className="mt-2 grid gap-2">
                            <input
                              value={draft.title}
                              onChange={(event) => setKnowledgeDrafts((curr) => ({ ...curr, [entry.knowledge_id]: { ...draft, title: event.target.value } }))}
                              className={INPUT_BASE}
                            />
                            <input
                              value={draft.category}
                              onChange={(event) => setKnowledgeDrafts((curr) => ({ ...curr, [entry.knowledge_id]: { ...draft, category: event.target.value } }))}
                              className={INPUT_BASE}
                            />
                            <textarea
                              rows={3}
                              value={draft.content}
                              onChange={(event) => setKnowledgeDrafts((curr) => ({ ...curr, [entry.knowledge_id]: { ...draft, content: event.target.value } }))}
                              className={`${INPUT_BASE} resize-y`}
                            />
                            <select
                              value={draft.status}
                              onChange={(event) => setKnowledgeDrafts((curr) => ({ ...curr, [entry.knowledge_id]: { ...draft, status: event.target.value } }))}
                              className={INPUT_BASE}
                            >
                              <option value="draft">draft</option>
                              <option value="active">active</option>
                              <option value="archived">archived</option>
                            </select>
                            <div className="flex flex-wrap gap-2">
                              <button type="button" className={BUTTON_SECONDARY} onClick={() => void saveKnowledgeDraft(entry.knowledge_id)}>
                                Save
                              </button>
                              <button type="button" className={BUTTON_SECONDARY} onClick={() => void archiveKnowledge(entry.knowledge_id)}>
                                Archive
                              </button>
                            </div>
                            {(entry.copied_from_tenant_id || entry.copied_from_record_id) && (
                              <p className="text-[11px] text-slate-500">
                                Copied from {entry.copied_from_tenant_id || "-"} / {entry.copied_from_record_id || "-"}
                              </p>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {activePanelTab === "workflows" && (
                <div className="mt-4 space-y-3">
                  <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/70 p-3 md:grid-cols-3">
                    <input value={workflowCopySourceTenant} onChange={(event) => setWorkflowCopySourceTenant(event.target.value)} placeholder="Source tenant ID" className={INPUT_BASE} />
                    <input value={workflowCopySourceId} onChange={(event) => setWorkflowCopySourceId(event.target.value)} placeholder="Source workflow ID" className={INPUT_BASE} />
                    <button type="button" className={BUTTON_SECONDARY} onClick={() => void copyWorkflow()}>
                      Copy Workflow (inactive)
                    </button>
                  </div>

                  <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                    <table className="min-w-full text-left text-xs text-slate-200">
                      <thead className="text-slate-400">
                        <tr>
                          <th className="py-1 pr-2">Workflow ID</th>
                          <th className="py-1 pr-2">Name</th>
                          <th className="py-1 pr-2">Version</th>
                          <th className="py-1 pr-2">Enabled</th>
                          <th className="py-1">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tenantWorkflows.map((workflow) => (
                          <tr key={workflow.workflow_id} className="border-t border-slate-800/70">
                            <td className="py-1 pr-2 font-mono text-[11px] text-slate-300">{workflow.workflow_id}</td>
                            <td className="py-1 pr-2">{workflow.workflow_name}</td>
                            <td className="py-1 pr-2">{workflow.version || "-"}</td>
                            <td className="py-1 pr-2">{workflow.enabled ? "Yes" : "No"}</td>
                            <td className="py-1 text-slate-500">Archive/disable endpoint not available yet.</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activePanelTab === "integrations" && (
                <div className="mt-4 space-y-3">
                  <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/70 p-3 md:grid-cols-2">
                    <select value={newIntegrationType} onChange={(event) => setNewIntegrationType(event.target.value)} className={INPUT_BASE}>
                      <option value="crm">crm</option>
                      <option value="carrier_portal">carrier_portal</option>
                      <option value="api">api</option>
                    </select>
                    <input value={newIntegrationName} onChange={(event) => setNewIntegrationName(event.target.value)} placeholder="Integration name" className={INPUT_BASE} />
                    <input value={newIntegrationSecret} onChange={(event) => setNewIntegrationSecret(event.target.value)} placeholder="Secret (write only)" className={INPUT_BASE} />
                    <input value={newIntegrationBaseUrl} onChange={(event) => setNewIntegrationBaseUrl(event.target.value)} placeholder="Base URL (optional)" className={INPUT_BASE} />
                    <button type="button" className={BUTTON_PRIMARY} onClick={() => void createIntegration()}>Save Integration Secret</button>
                    <p className="self-center text-xs text-slate-500">After save, secret is masked and never shown in plaintext.</p>
                  </div>

                  <div className="space-y-2">
                    {tenantIntegrations.map((integration) => (
                      <div key={integration.integration_id} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-50">{integration.name}</p>
                          <span className="text-xs text-slate-400">{integration.status}</span>
                        </div>
                        <p className="mt-1 text-xs text-slate-400">Type: {integration.integration_type} • Secret: {integration.secret_masked || "(masked)"}</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            className={BUTTON_SECONDARY}
                            onClick={() => {
                              setEditingIntegrationId(integration.integration_id);
                              setEditIntegrationName(integration.name);
                              setEditIntegrationStatus(integration.status);
                              setEditIntegrationSecret("");
                            }}
                          >
                            Edit
                          </button>
                          <button type="button" className={BUTTON_SECONDARY} onClick={() => void archiveIntegration(integration.integration_id)}>
                            Archive
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>

                  {editingIntegrationId && (
                    <div className="rounded-lg border border-amber-300/30 bg-amber-500/10 p-3">
                      <p className="text-xs uppercase tracking-[0.14em] text-amber-200">Edit integration</p>
                      <div className="mt-2 grid gap-2 md:grid-cols-2">
                        <input value={editIntegrationName} onChange={(event) => setEditIntegrationName(event.target.value)} placeholder="Name" className={INPUT_BASE} />
                        <select value={editIntegrationStatus} onChange={(event) => setEditIntegrationStatus(event.target.value)} className={INPUT_BASE}>
                          <option value="active">active</option>
                          <option value="archived">archived</option>
                          <option value="disabled">disabled</option>
                        </select>
                        <input value={editIntegrationSecret} onChange={(event) => setEditIntegrationSecret(event.target.value)} placeholder="Replace secret (optional)" className={INPUT_BASE} />
                      </div>
                      <div className="mt-2 flex gap-2">
                        <button type="button" className={BUTTON_PRIMARY} onClick={() => void saveIntegrationUpdate()}>Save</button>
                        <button type="button" className={BUTTON_SECONDARY} onClick={() => setEditingIntegrationId(null)}>Cancel</button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {activePanelTab === "bundles" && (
                <div className="mt-4 space-y-3">
                  <div className="grid gap-2 rounded-lg border border-slate-800 bg-slate-900/70 p-3 md:grid-cols-2">
                    <input value={newBundleId} onChange={(event) => setNewBundleId(event.target.value)} placeholder="Bundle ID (optional)" className={INPUT_BASE} />
                    <input value={newBundleName} onChange={(event) => setNewBundleName(event.target.value)} placeholder="Bundle name" className={INPUT_BASE} />
                    <input value={newBundleSourceTenant} onChange={(event) => setNewBundleSourceTenant(event.target.value)} placeholder="Source tenant ID" className={INPUT_BASE} />
                    <input value={newBundleWorkflowId} onChange={(event) => setNewBundleWorkflowId(event.target.value)} placeholder="Source workflow ID" className={INPUT_BASE} />
                    <button type="button" className={BUTTON_PRIMARY} onClick={() => void createBundle()}>Create Bundle</button>
                  </div>

                  <div className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <select value={bundleApplyId} onChange={(event) => setBundleApplyId(event.target.value)} className={INPUT_BASE}>
                        <option value="">Select bundle</option>
                        {bundles.map((bundle) => (
                          <option key={bundle.bundle_id} value={bundle.bundle_id}>{bundle.name} ({bundle.bundle_id})</option>
                        ))}
                      </select>
                      <button type="button" className={BUTTON_SECONDARY} onClick={() => void applyBundle()}>
                        Apply to Tenant
                      </button>
                    </div>
                    {bundleResult && <p className="mt-2 text-xs text-emerald-200">{bundleResult}</p>}
                  </div>

                  <div className="space-y-2">
                    {bundles.map((bundle) => (
                      <div key={bundle.bundle_id} className="rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                        <p className="text-sm font-semibold text-slate-50">{bundle.name}</p>
                        <p className="text-xs text-slate-400">{bundle.bundle_id} • Templates: {bundle.templates.length}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {activePanelTab === "workers" && (
                <div className="mt-4 space-y-3">
                  <div className="overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                    <table className="min-w-full text-left text-xs text-slate-200">
                      <thead className="text-slate-400">
                        <tr>
                          <th className="py-1 pr-2">Worker</th>
                          <th className="py-1 pr-2">Tenant</th>
                          <th className="py-1 pr-2">Status</th>
                          <th className="py-1 pr-2">Version</th>
                          <th className="py-1 pr-2">Mode</th>
                          <th className="py-1">Last seen</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tenantWorkers.map((worker) => (
                          <tr key={worker.machine_uuid} className="border-t border-slate-800/70">
                            <td className="py-1 pr-2 font-mono text-[11px] text-slate-300">{worker.machine_name || worker.machine_uuid}</td>
                            <td className="py-1 pr-2 text-slate-400">{worker.tenant_id || selectedTenant.tenant_id}</td>
                            <td className="py-1 pr-2">{worker.status || "unknown"}</td>
                            <td className="py-1 pr-2">{worker.worker_version || "-"}</td>
                            <td className="py-1 pr-2">{worker.execution_mode || "-"}</td>
                            <td className="py-1 text-slate-400">{fmtTime(worker.last_seen)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {activePanelTab === "audit" && (
                <div className="mt-4 overflow-x-auto rounded-lg border border-slate-800 bg-slate-900/70 p-3">
                  <table className="min-w-full text-left text-xs text-slate-200">
                    <thead className="text-slate-400">
                      <tr>
                        <th className="py-1 pr-2">Time</th>
                        <th className="py-1 pr-2">Event</th>
                        <th className="py-1 pr-2">Actor</th>
                        <th className="py-1 pr-2">Role</th>
                        <th className="py-1 pr-2">Target</th>
                        <th className="py-1">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tenantAudit.map((entry) => (
                        <tr key={entry.id} className="border-t border-slate-800/70">
                          <td className="py-1 pr-2 text-slate-400">{fmtTime(entry.created_at)}</td>
                          <td className="py-1 pr-2">{entry.event_type}</td>
                          <td className="py-1 pr-2">{entry.actor_user_name || "system"}</td>
                          <td className="py-1 pr-2">{entry.actor_role || "-"}</td>
                          <td className="py-1 pr-2">{entry.target_type || "-"} / {entry.target_id || "-"}</td>
                          <td className="py-1">{entry.status_code ?? "-"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </section>
  );
}
