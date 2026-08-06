import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'
import 'highlight.js/styles/github.css' // Base styles

const MARKDOWN_URI_PATTERN = /^(?:(?:https?|mailto|tel|quick|canvas|blob):|data:image\/(?:png|gif|jpe?g|webp);base64,|(?:[^a-z]|[a-z0-9._~-]+(?:[/?#]|$)))/i

export const sanitizeMarkdownHtml = (html: string): string => {
  return DOMPurify.sanitize(html, {
    USE_PROFILES: { html: true },
    ALLOW_DATA_ATTR: true,
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'form', 'input', 'button', 'textarea', 'select', 'option'],
    FORBID_ATTR: ['style'],
    ALLOWED_URI_REGEXP: MARKDOWN_URI_PATTERN,
  }) as string
}

const md: MarkdownIt = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  highlight: null
})

// Override fence rule to prevent double wrapping
md.renderer.rules.fence = function (tokens, idx, _options, _env, _self) {
  const token = tokens[idx]!;
  const info = token.info ? md.utils.unescapeAll(token.info).trim() : '';
  let langName = '';
  let highlighted: string;

  if (info) {
    langName = info.split(/\s+/g)[0] || '';
  }

  if (langName && hljs.getLanguage(langName)) {
    try {
      highlighted = hljs.highlight(token.content, { language: langName, ignoreIllegals: true }).value;
    } catch (_) {
      highlighted = md.utils.escapeHtml(token.content);
    }
  } else {
    highlighted = md.utils.escapeHtml(token.content);
  }

  // Custom wrapper structure
  return `<div class="code-block-wrapper"><pre class="hljs"><code>${highlighted}</code></pre><span class="code-copy-btn" title="复制代码"></span></div>`;
};

// Allow "quick:" protocol in links
const defaultValidateLink = md.validateLink;
md.validateLink = (url) => {
  const str = url.trim().toLowerCase();
  return defaultValidateLink(url) || str.startsWith('quick:');
};

// Custom rule to open links in new window
const defaultRender = md.renderer.rules.link_open || function(tokens, idx, options, _env, self) {
  return self.renderToken(tokens, idx, options);
};

md.renderer.rules.link_open = function (tokens, idx, options, _env, self) {
  const token = tokens[idx]!;
  if (!token.attrs) {
    token.attrs = [];
  }
  
  const hAttr = token.attrIndex('href');
  if (hAttr >= 0 && token.attrs!) {
    const href = token.attrs![hAttr]![1];

    // quick: 是站内快捷动作，不能当外链开新页（否则移动端易出现点两次才生效）
    if (href.startsWith('quick:')) {
      const classIndex = token.attrIndex('class');
      const className = 'quick-action-btn';
      if (classIndex < 0) {
        token.attrPush(['class', className]);
      } else {
        token.attrs![classIndex]![1] = className;
      }
      token.attrPush(['data-quick-link', 'true']);
    } else if (/^https?:\/\//.test(href)) {
      const aIndex = token.attrIndex('target');
      if (aIndex < 0) {
        token.attrPush(['target', '_blank']);
      } else {
        token.attrs![aIndex]![1] = '_blank';
      }

      const rIndex = token.attrIndex('rel');
      if (rIndex < 0) {
        token.attrPush(['rel', 'noopener noreferrer']);
      }
    }
  }
  return defaultRender(tokens, idx, options, _env, self);
};

const normalizePipeTables = (content: string) => {
  return content
    .split('\n')
    .map((line) => {
      const trimmed = line.trim();
      if (!trimmed.startsWith('|') || !trimmed.endsWith('|') || !trimmed.includes('||')) {
        return line;
      }

      const cells = trimmed
        .slice(1, -1)
        .split(/\s*\|\|\s*/)
        .map((cell) => cell.trim())
        .filter(Boolean);

      const isSeparatorCell = (cell: string) => /^:?-{2,}:?$/.test(cell);
      const firstSeparator = cells.findIndex((cell) => isSeparatorCell(cell));
      if (firstSeparator <= 0) return line;

      const columnCount = firstSeparator;
      const separatorCount = cells
        .slice(firstSeparator, firstSeparator + columnCount)
        .filter((cell) => isSeparatorCell(cell)).length;
      const bodyCells = cells.slice(firstSeparator + columnCount);
      if (separatorCount !== columnCount || bodyCells.length === 0 || bodyCells.length % columnCount !== 0) {
        return line;
      }

      const rows = [
        cells.slice(0, columnCount),
        cells.slice(firstSeparator, firstSeparator + columnCount),
      ];
      for (let i = 0; i < bodyCells.length; i += columnCount) {
        rows.push(bodyCells.slice(i, i + columnCount));
      }
      return rows.map((row) => `| ${row.join(' | ')} |`).join('\n');
    })
    .join('\n');
};

export const renderMarkdown = (content: string) => {
  return sanitizeMarkdownHtml(md.render(normalizePipeTables(content)))
}

/** 画布/预览场景：保留单行换行，便于 .md 纯文本阅读 */
const mdPreview = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
  breaks: true,
  highlight: null,
})
mdPreview.renderer.rules.fence = md.renderer.rules.fence!
mdPreview.validateLink = md.validateLink

export const renderMarkdownPreview = (content: string) => {
  return sanitizeMarkdownHtml(mdPreview.render(normalizePipeTables(content)))
}
