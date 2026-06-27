'use client';

import { memo, useState, useCallback } from 'react';
import { Highlight, type PrismTheme } from 'prism-react-renderer';
import { Check, Copy, ChevronDown } from 'lucide-react';

type Props = {
  content: string;
  variant?: 'default' | 'compact';
  streaming?: boolean;
};

// Warm syntax theme using our CSS variables
const warmTheme: PrismTheme = {
  plain: { color: 'var(--code-fg)', backgroundColor: 'transparent' },
  styles: [
    { types: ['comment', 'prolog', 'doctype'], style: { color: 'var(--code-comment)', fontStyle: 'italic' } },
    { types: ['string', 'attr-value', 'template-string'], style: { color: 'var(--code-string)' } },
    { types: ['keyword', 'selector', 'important'], style: { color: 'var(--code-keyword)' } },
    { types: ['function'], style: { color: 'var(--code-fn)' } },
    { types: ['number', 'boolean'], style: { color: 'var(--code-number)' } },
    { types: ['operator', 'punctuation'], style: { color: 'var(--code-fg)' } },
    { types: ['class-name', 'builtin', 'constant'], style: { color: 'var(--code-fn)' } },
    { types: ['tag'], style: { color: 'var(--code-keyword)' } },
    { types: ['property', 'attr-name'], style: { color: 'var(--code-number)' } },
  ],
};

/** macOS-style terminal window with traffic lights */
function TerminalChrome({
  title,
  children,
  showHeader = true,
}: {
  title?: string;
  children: React.ReactNode;
  showHeader?: boolean;
}) {
  return (
    <div
      className="overflow-hidden my-3 rounded-xl border"
      style={{ borderColor: 'var(--border)', background: 'var(--code-bg)' }}
    >
      {showHeader && (
        <div
          className="flex items-center gap-2 px-3 py-2 border-b"
          style={{ borderColor: 'var(--border)', background: 'var(--surface-2)' }}
        >
          <div className="flex gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#ff5f57' }} />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#febc2e' }} />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: '#28c840' }} />
          </div>
          {title && (
            <span className="ml-1 text-[10px] mono" style={{ color: 'var(--text-3)' }}>
              {title}
            </span>
          )}
        </div>
      )}
      <div className="overflow-x-auto">{children}</div>
    </div>
  );
}

/** Code block with line numbers, copy button, language label */
function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [code]);

  return (
    <TerminalChrome title={language || 'code'}>
      <div className="relative group">
        <Highlight theme={warmTheme} code={code.trimEnd()} language={language || 'text'}>
          {({ className, style, tokens, getLineProps, getTokenProps }) => (
            <pre
              className={className}
              style={{ ...style, padding: '14px', margin: 0, fontSize: '13px', lineHeight: '1.5', fontFamily: 'var(--font-mono, "SF Mono", monospace)' }}
            >
              {tokens.map((line, i) => {
                const lineProps = getLineProps({ line });
                return (
                  <div key={i} {...lineProps} style={{ ...lineProps.style, display: 'table-row' }}>
                    <span
                      className="select-none"
                      style={{
                        display: 'table-cell',
                        paddingRight: '14px',
                        textAlign: 'right',
                        userSelect: 'none',
                        color: 'var(--text-faint)',
                        minWidth: '2.5em',
                        opacity: 0.5,
                      }}
                    >
                      {i + 1}
                    </span>
                    <span style={{ display: 'table-cell' }}>
                      {line.map((token, key) => {
                        const tokenProps = getTokenProps({ token });
                        return <span key={key} {...tokenProps} />;
                      })}
                    </span>
                  </div>
                );
              })}
            </pre>
          )}
        </Highlight>
        {/* Copy button */}
        <button
          onClick={handleCopy}
          className="absolute top-2 right-2 p-1.5 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
          style={{ background: 'var(--surface-3)', color: 'var(--text-2)' }}
          title="Copy"
        >
          {copied ? <Check size={14} style={{ color: 'var(--accent)' }} /> : <Copy size={14} />}
        </button>
      </div>
    </TerminalChrome>
  );
}

/** Collapsible section for long content */
function CollapsibleSection({ summary, children }: { summary: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="my-2 rounded-lg border overflow-hidden"
      style={{ borderColor: 'var(--border)' }}
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary
        className="cursor-pointer px-3 py-2 text-[12px] select-none flex items-center gap-1"
        style={{ color: 'var(--text-2)', background: 'var(--surface)' }}
      >
        <ChevronDown size={12} className={open ? '' : '-rotate-90'} style={{ transition: 'transform .15s' }} />
        {summary}
      </summary>
      <div className="px-3 py-2 text-[13px]" style={{ color: 'var(--text-2)' }}>
        {children}
      </div>
    </details>
  );
}

// Inline markdown renderer — uses marked for the heavy lifting,
// then post-processes the HTML to replace code fences with React CodeBlocks.
function renderMarkdown(text: string): string {
  // Strip model-specific tags
  let cleaned = text
    .replace(/<minimax:tool_call>[\s\S]*?<\/minimax:tool_call>/g, '')
    .replace(/<invoke[\s\S]*?<\/invoke>/g, '')
    .replace(/<parameter[\s\S]*?<\/parameter>/g, '')
    .replace(/<\/?(?:minimax|invoke|parameter|function_calls)[^>]*>/g, '');

  // Use marked for GFM parsing
  // We let marked produce the full HTML, then the consumer injects it.
  // Code fence handling is done client-side by scanning for <pre><code> blocks.
  return cleaned;
}

function MarkdownRendererBase({ content, variant = 'default', streaming = false }: Props) {
  if (!content) return null;

  // Use marked via dynamic import to avoid SSR issues
  const cleaned = renderMarkdown(content);

  // Parse with a regex-based approach to split code blocks from regular markdown
  const parts: Array<{ type: 'code'; code: string; lang: string } | { type: 'html'; html: string }> = [];
  const codeFenceRegex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = codeFenceRegex.exec(cleaned)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ type: 'html', html: cleaned.slice(lastIndex, match.index) });
    }
    parts.push({ type: 'code', code: match[2], lang: match[1] || 'text' });
    lastIndex = codeFenceRegex.lastIndex;
  }
  if (lastIndex < cleaned.length) {
    parts.push({ type: 'html', html: cleaned.slice(lastIndex) });
  }

  return (
    <div
      className={variant === 'compact' ? 'text-[12px]' : 'text-[14px]'}
      style={{ lineHeight: '1.75' }}
    >
      {parts.map((part, i) => {
        if (part.type === 'code') {
          return <CodeBlock key={i} code={part.code} language={part.lang} />;
        }
        // For HTML parts, render as markdown via dangerouslySetInnerHTML
        // Parse inline markdown with a simple approach
        return (
          <div
            key={i}
            className="md-content"
            dangerouslySetInnerHTML={{
              __html: parseInlineMarkdown(part.html),
            }}
          />
        );
      })}
    </div>
  );
}

/** Simple inline markdown parser (bold, italic, links, inline code, lists, headings) */
function parseInlineMarkdown(text: string): string {
  let html = text;

  // Headings
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  // Bold + italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  // Inline code (not in code blocks)
  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  // Links
  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );

  // Images
  html = html.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    '<img src="$2" alt="$1" style="max-width:100%;border-radius:8px;margin:8px 0" />',
  );

  // Blockquote
  html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');

  // HR
  html = html.replace(/^---$/gm, '<hr/>');

  // Unordered list items
  html = html.replace(/^[\*\-] (.+)$/gm, '<li>$1</li>');
  if (html.includes('<li>')) {
    html = html.replace(/(<li>[\s\S]*?<\/li>(\n|$))+/g, (match) => `<ul>${match}</ul>`);
  }

  // Ordered list items
  html = html.replace(/^\d+\. (.+)$/gm, '<li class="ol-item">$1</li>');

  // Tables (simple GFM)
  html = html.replace(
    /^\|(.+)\|$/gm,
    (match) => {
      const cells = match.split('|').filter((c) => c.trim());
      if (cells.every((c) => /^[\s-:]+$/.test(c))) return ''; // separator row
      const isHeader = match.includes('---');
      return `<tr>${cells.map((c) => `<td>${c.trim()}</td>`).join('')}</tr>`;
    },
  );
  if (html.includes('<tr>')) {
    html = '<table>' + html.replace(/(<tr>[\s\S]*?<\/tr>\n?)+/g, (m) => m) + '</table>';
  }

  // Paragraphs: wrap loose text in <p>
  html = html.replace(/^(?!<[a-z])((?!<\/?[a-z]).+)$/gim, '<p>$1</p>');

  // Line breaks
  html = html.replace(/\n/g, '<br/>');

  // Clean up: remove empty paragraphs
  html = html.replace(/<p><\/p>/g, '');
  html = html.replace(/<p>(<br\/>)*<\/p>/g, '');

  return html;
}

export default memo(MarkdownRendererBase);
export { MarkdownRendererBase as MarkdownRenderer, CodeBlock, TerminalChrome, CollapsibleSection };
