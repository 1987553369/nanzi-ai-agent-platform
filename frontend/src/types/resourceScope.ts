export type ResourceScopeGroupKey =
  | "datasets"
  | "knowledge_bases"
  | "skills"
  | "mcp_tools";

export type ResourceScopeGroup = {
  key: ResourceScopeGroupKey;
  label: string;
  shortLabel?: string;
  hint: string;
};

export type ResourceScopeChip = {
  key: string;
  label: string;
  orphan?: boolean;
  item: any;
};
