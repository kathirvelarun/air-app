import type { InvestigationResponse, LiveStatus } from '../types/investigation';

export type InvestigationSnapshot = {
  uuid: string;
  status: LiveStatus;
  startedAt: number;
  finishedAt?: number;
  result?: InvestigationResponse;
  error?: string;
};
const prefix = 'air.investigation.v1.';
export const syncEvent = 'air-investigation-update';

export function readInvestigation(uuid: string): InvestigationSnapshot | null {
  try {
    const value = JSON.parse(localStorage.getItem(prefix + uuid) ?? 'null');
    return value?.uuid === uuid && typeof value.startedAt === 'number' ? value : null;
  } catch { return null; }
}

export function publishInvestigation(snapshot: InvestigationSnapshot): void {
  // Storage events update other tabs; the custom event updates this tab.
  localStorage.setItem(prefix + snapshot.uuid, JSON.stringify(snapshot));
  window.dispatchEvent(new Event(syncEvent));
}

export function subscribeInvestigations(refresh: () => void): () => void {
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key.startsWith(prefix)) refresh();
  };
  window.addEventListener('storage', onStorage);
  window.addEventListener(syncEvent, refresh);
  return () => {
    window.removeEventListener('storage', onStorage);
    window.removeEventListener(syncEvent, refresh);
  };
}
