export type CreatedResponse = { created: boolean };
export type ExistsResponse = { exists: boolean };
export type UserRequestItem = {
  arxiv_id: string;
  title?: string | null;
  authors?: string | null;
  is_processed?: boolean;
  processed_slug?: string | null;
  created_at?: string | null;
};

const API_BASE = '/api';

function buildAuthHeaders(authProviderId: string, extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  headers.set('X-Auth-Provider-Id', authProviderId);
  return headers;
}

export async function addUserRequest(
  arxivId: string,
  authProviderId: string
): Promise<CreatedResponse> {
  const resp = await fetch(`${API_BASE}/users/me/requests/${encodeURIComponent(arxivId)}`, {
    method: 'POST',
    headers: buildAuthHeaders(authProviderId),
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to add request (${resp.status})`);
  }
  return resp.json();
}

export async function doesUserRequestExist(
  arxivId: string,
  authProviderId: string
): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/users/me/requests/${encodeURIComponent(arxivId)}`, {
    headers: buildAuthHeaders(authProviderId),
    cache: 'no-store' as RequestCache,
  });
  if (!resp.ok) return false;
  const data: ExistsResponse = await resp.json();
  return Boolean(data?.exists);
}

export async function listMyRequests(authProviderId: string): Promise<UserRequestItem[]> {
  const resp = await fetch(`${API_BASE}/users/me/requests`, {
    headers: buildAuthHeaders(authProviderId),
    cache: 'no-store' as RequestCache,
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to fetch requests (${resp.status})`);
  }
  return resp.json();
}

export async function removeUserRequest(
  arxivId: string,
  authProviderId: string
): Promise<{ deleted: boolean }> {
  const resp = await fetch(`${API_BASE}/users/me/requests/${encodeURIComponent(arxivId)}`, {
    method: 'DELETE',
    headers: buildAuthHeaders(authProviderId),
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to remove request (${resp.status})`);
  }
  return resp.json();
}


