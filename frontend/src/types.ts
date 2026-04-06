export type CatalogApp = {
  id: string;
  title: string;
  description: string;
  tags: string[];
  input_datasets: string[];
  output_datasets: string[];
  saref_type: string;
  version: string;
  publisher: string;
  created_at: string;
  updated_at: string;
};

export type CatalogResponse = {
  total: number;
  page: number;
  page_size: number;
  apps: CatalogApp[];
};

export type RecommendedApp = {
  app: CatalogApp;
  score: number;
  vector_score?: number;
  keyword_score?: number;
  saref_boost?: number;
};

export type ChatResponse = {
  session_id: string;
  message: string;
  intent: string;
  apps: RecommendedApp[];
};
