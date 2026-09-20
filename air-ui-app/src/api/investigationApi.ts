import type { InvestigateRequest, InvestigationResponse } from '../types/investigation';

export const INVESTIGATE_URL = import.meta.env.VITE_INVESTIGATE_URL || '/api/v1/incidents/investigate';

export async function investigateIncident(request: InvestigateRequest, signal?: AbortSignal): Promise<InvestigationResponse> {
  let response: Response;
  try {
    response = await fetch(INVESTIGATE_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
      signal,
    });
  } catch {
    throw new Error(`Could not reach ${INVESTIGATE_URL}. Confirm the AIR API is running and reachable from this browser (CORS enabled for this origin).`);
  }
  if (!response.ok) {
    const text = await response.text().catch(() => '');
    throw new Error(`Investigate API returned ${response.status} ${response.statusText}${text ? `: ${text.slice(0, 300)}` : ''}`);
  }
  return response.json() as Promise<InvestigationResponse>;
}