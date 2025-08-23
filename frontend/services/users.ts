export type CreatedResponse = { created: boolean };
export type ExistsResponse = { exists: boolean };

const API_BASE = '/api';

function buildAuthHeaders(authProviderId: string, extra?: HeadersInit): Headers {
  const headers = new Headers(extra);
  headers.set('X-Auth-Provider-Id', authProviderId);
  return headers;
}

export async function addPaperToUserList(
  paperUuid: string,
  authProviderId: string
): Promise<CreatedResponse> {
  const resp = await fetch(`${API_BASE}/users/me/list/${encodeURIComponent(paperUuid)}`, {
    method: 'POST',
    headers: buildAuthHeaders(authProviderId),
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to add to list (${resp.status})`);
  }
  return resp.json();
}

export async function isPaperInUserList(
  paperUuid: string,
  authProviderId: string
): Promise<boolean> {
  const resp = await fetch(`${API_BASE}/users/me/list/${encodeURIComponent(paperUuid)}`, {
    headers: buildAuthHeaders(authProviderId),
    cache: 'no-store' as RequestCache,
  });
  if (!resp.ok) return false;
  const data: ExistsResponse = await resp.json();
  return Boolean(data?.exists);
}

export async function removePaperFromUserList(
  paperUuid: string,
  authProviderId: string
): Promise<{ deleted: boolean }> {
  const resp = await fetch(`${API_BASE}/users/me/list/${encodeURIComponent(paperUuid)}`, {
    method: 'DELETE',
    headers: buildAuthHeaders(authProviderId),
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => '');
    throw new Error(txt || `Failed to remove from list (${resp.status})`);
  }
  return resp.json();
}


