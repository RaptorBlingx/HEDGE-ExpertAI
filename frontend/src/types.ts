export type Locale = "en" | "de" | "fr" | "es" | "it" | "nl" | "pt" | "tr";

export type LocalizedText = Record<Locale, string | undefined> & { en: string };

export type DataContract = {
  name: string;
  description: string;
  media_type: string;
  schema_uri?: string;
  unit_uri?: string;
  frequency?: string;
  data_classification: string;
};

export type SemanticAnnotation = {
  term_uri: string;
  label: string;
  ontology_uri: string;
  ontology_version: string;
  relation: string;
  provenance: string;
  review_status: string;
  confidence?: number;
};

export type CatalogApp = {
  schema_version: "2.0";
  id: string;
  slug: string;
  title: LocalizedText;
  summary: LocalizedText;
  description: string;
  localized_keywords: Record<Locale, string[]>;
  tags: string[];
  domains: string[];
  capabilities: string[];
  industries: string[];
  supported_languages: Locale[];
  protocols: string[];
  standards: string[];
  inputs: DataContract[];
  outputs: DataContract[];
  app_url: string;
  documentation_url: string;
  publisher: { name: string; website?: string; support_url?: string };
  lifecycle: { version: string; status: string; released_at?: string; updated_at?: string };
  semantic_annotations: SemanticAnnotation[];
  provenance: { synthetic: boolean; source: string; review_status: string };
};

export type CatalogResponse = {
  schema_version: "2.0";
  total: number;
  page: number;
  page_size: number;
  apps: CatalogApp[];
};

export type RecommendedApp = {
  app: CatalogApp;
  rank: number;
  relevance: "high" | "medium" | "low";
  evidence_fields: string[];
};

export type ChatResponse = {
  schema_version: "2.0";
  session_id: string;
  message: string;
  intent: string;
  apps: RecommendedApp[];
  impression_id?: string;
};
