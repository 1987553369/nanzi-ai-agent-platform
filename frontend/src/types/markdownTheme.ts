export const MARKDOWN_THEMES = [
  "default",
  "minimal",
  "academic",
  "apple",
  "warm",
  "compact",
  "bauhaus",
  "editorial",
  "zen",
] as const;

export type MarkdownTheme = (typeof MARKDOWN_THEMES)[number];

export const normalizeMarkdownTheme = (value: unknown): MarkdownTheme => {
  const theme = String(value || "") as MarkdownTheme;
  return MARKDOWN_THEMES.includes(theme) ? theme : "default";
};
