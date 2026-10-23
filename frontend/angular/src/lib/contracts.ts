/** Existing ExpertAI v2 contracts; native identity is never a display label. */
export interface StoreApp {
  id: string;
  store_id: string;
  app_id: string;
  name: string;
  provider?: string;
  description?: string;
  source_evidence?: Record<string, string>;
  readme_status?: string;
}
export interface AppResult {
  app: StoreApp;
  rank?: number;
  suitability?: { status: string; evidence_fields?: string[] };
}
export interface InspectAction { type: 'inspect'; store_id: string; app_id: string }
export interface ChatRequest {
  session_id: string | null;
  message: string;
  locale: 'en';
  filters: Record<string, never>;
  app_action?: InspectAction;
}
export interface StreamEvent {
  type: string;
  stage?: string;
  content?: string;
  apps?: AppResult[];
  session_id?: string;
  impression_id?: string;
  title?: string;
  detail?: string;
  generation?: { source?: string; model_completed?: boolean };
  decision?: { outcome?: string; reason?: string };
}
export interface Catalogue { apps: StoreApp[]; total: number; next_offset: number | null }
export interface History { messages: { role: string; content: string }[]; apps?: AppResult[] }
export interface ServiceStatus { source: string; catalogue: string; deployed_commit: string }
export interface ExpertConfig {
  /** Same-origin gateway by default. Browser credentials must be user tokens, never M2M secrets. */
  apiBase: string;
  sessionKey: string;
  getAccessToken?: () => Promise<string | null>;
}
export const identity = (app: StoreApp): string => JSON.stringify([app.store_id, app.app_id]);
export function isStoreApp(value: unknown): value is StoreApp {
  if (!value || typeof value !== 'object') return false;
  const v = value as Record<string, unknown>;
  return ['id', 'store_id', 'app_id', 'name'].every(k => typeof v[k] === 'string');
}
