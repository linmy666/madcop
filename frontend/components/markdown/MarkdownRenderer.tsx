'use client';

import { memo, useState, useCallback, useEffect } from 'react';
import { Highlight, type PrismTheme } from 'prism-react-renderer';
import { Check, Copy, ChevronDown, ChevronUp, ChevronRight } from 'lucide-react';

type Props = {
  content: string;
  variant?: 'default' | 'compact';
  streaming?: boolean;
};

// Warm syntax theme using our CSS variables
const theme: PrismTheme = {
  plain: { color: 'var(--code-fg)', backgroundColor: 'transparent' },
  styles: [
    { types: ['comment', 'prolog', 'doctype'], style: { color: 'var(--code-comment)', fontStyle: 'italic' } },
    { types: ['string', 'attr-value', 'template-string'], style: { color: 'var(--code-string)' } },
    { types: ['keyword', 'selector', 'important'], style: { color: 'var(--code-keyword)' } },
    { types: ['function'], style: { color: 'var(--code-fn)' } },
    { types: ['number', 'boolean'], style: { color: 'var(--code-number)' } },
    { types: ['operator', 'punctuation'], style: { color: 'var(--code-fg)' } },
    { types: ['class-name', 'builtin', 'constant'], style: { color: 'var(--code-type)' } },
    { types: ['tag'], style: { color: 'var(--code-keyword)' } },
    { types: ['property', 'attr-name'], style: { color: 'var(--code-number)' } },
  ],
};

/** macOS-style terminal window decoration */
function TerminalChrome({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <div
      className="overflow-hidden my-2.5 rounded-xl border"
      style={{
        background: 'var(--surface-code)',
        borderColor: 'var(--border)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
      <div
        className="flex items-center gap-1.5 px-3 py-1.5 border-b"
        style={{
          borderColor: 'var(--border)',
          background: 'var(--surface-1)',
        }}
      >
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#ff5f57' }} />
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#febc2e' }} />
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#28c840' }} />
        {title && (
          <span
            className="ml-2 text-[10px] mono uppercase tracking-wide"
            style={{ color: 'var(--text-3)' }}
          >
            {title}
          </span>
        )}
      </div>
      <div>{children}</div>
    </div>
  );
}

function CodeBlock({ code, language }: { code: string; language: string }) {
  const [copied, setCopied] = useState(false);
  const [collapsed, setCollapsed] = useState(code.split('\n').length > 20);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [code]);

  const lines = code.split('\n');

  return (
    <TerminalChrome title={language || 'code'}>
      <div className="relative group">
        {/* Floating action bar */}
        <div className="absolute top-1.5 right-1.5 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="h-6 w-6 flex items-center justify-center rounded transition-colors"
            style={{ background: 'var(--surface-2)', color: 'var(--text-2)' }}
            title={collapsed ? 'Expand' : 'Collapse'}
          >
            {collapsed ? <ChevronDown size={11} /> : <ChevronUp size={11} />}
          </button>
          <button
            onClick={handleCopy}
            className="h-6 w-6 flex items-center justify-center rounded transition-colors"
            style={{
              background: copied ? 'var(--accent-dim)' : 'var(--surface-2)',
              color: copied ? 'var(--accent)' : 'var(--text-2)',
            }}
            title="Copy"
          >
            {copied ? <Check size={11} /> : <Copy size={11} />}
          </button>
        </div>

        {collapsed ? (
          <div
            className="px-4 py-3 text-[12px] mono"
            style={{ color: 'var(--text-2)' }}
          >
            {lines[0].slice(0, 120)}
            {lines.length > 1 && (
              <span style={{ color: 'var(--text-faint)' }}>
                {'  '}... +{lines.length - 1} more lines
              </span>
            )}
          </div>
        ) : (
          <Highlight theme={theme} code={code} language={language || 'text'}>
            {({ className, style, tokens, getLineProps, getTokenProps }) => (
              <pre
                className={className}
                style={{
                  ...style,
                  padding: '14px 16px',
                  margin: 0,
                  fontSize: '12.5px',
                  lineHeight: '1.6',
                  fontFamily: 'var(--font-mono)',
                  overflow: 'auto',
                  color: 'var(--code-fg)',
                  background: 'transparent',
                }}
              >
                {tokens.map((line, i) => {
                  const lineProps = getLineProps({ line });
                  return (
                    <div
                      key={i}
                      {...lineProps}
                      style={{ ...lineProps.style, display: 'table-row' }}
                    >
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
        )}
      </div>
    </TerminalChrome>
  );
}

/** Collapsible section for long content */
function CollapsibleSection({ summary, children }: { summary: string; children: React.ReactNode }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="my-2 rounded-md border overflow-hidden"
      style={{ borderColor: 'var(--border)' }}
      open={open}
      onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}
    >
      <summary
        className="cursor-pointer px-3 py-1.5 text-[12px] select-none flex items-center gap-1"
        style={{ color: 'var(--text-2)', background: 'var(--surface-1)' }}
      >
        <ChevronRight
          size={11}
          className={open ? 'rotate-90' : ''}
          style={{ transition: 'transform .15s' }}
        />
        {summary}
      </summary>
      <div className="px-3 py-2 text-[12px]" style={{ color: 'var(--text-2)' }}>
        {children}
      </div>
    </details>
  );
}

function parseInlineMarkdown(text: string): string {
  let html = text;

  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

  html = html.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

  html = html.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener">$1</a>',
  );

  html = html.replace(
    /!\[([^\]]*)\]\(([^)]+)\)/g,
    '<img src="$2" alt="$1" style="max-width:100%;border-radius:8px;margin:8px 0" />',
  );

  html = html.replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>');
  html = html.replace(/^---$/gm, '<hr/>');

  html = html.replace(/^[\*\-] (.+)$/gm, '<li>$1</li>');
  if (html.includes('<li>')) {
    html = html.replace(/(<li>[\s\S]*?<\/li>(\n|$))+/g, (match) => `<ul>${match}</ul>`);
  }

  html = html.replace(/^\d+\. (.+)$/gm, '<li class="ol-item">$1</li>');
  html = html.replace(
    /^\|(.+)\|$/gm,
    (match) => {
      const cells = match.split('|').filter((c) => c.trim());
      if (cells.every((c) => /^[\s-:]+$/.test(c))) return '';
      const isHeader = match.includes('---');
      return `<tr>${cells.map((c) => `<td>${c.trim()}</td>`).join('')}</tr>`;
    },
  );
  if (html.includes('<tr>')) {
    html = '<table>' + html.replace(/(<tr>[\s\S]*?<\/tr>\n?)+/g, (m) => m) + '</table>';
  }

  html = html.replace(/^(?!<[a-z])((?!<\/?[a-z]).+)$/gim, '<p>$1</p>');
  html = html.replace(/\n/g, '<br/>');
  html = html.replace(/<p><\/p>/g, '');
  html = html.replace(/<p>(<br\/>)*<\/p>/g, '');

  return html;
}

function MarkdownRendererBase({ content, variant = 'default' }: Props) {
  const [version, setVersion] = useState(0);

  // Force re-render on content change so streaming incremental updates render
  useEffect(() => { setVersion((v) => v + 1); }, [content]);
  if (!content) return null;

  let cleaned = content
    .replace(/<minimax:tool_call>[\s\S]*?<\/minimax:tool_call>/g, '')
    .replace(/<invoke[\s\S]*?<\/invoke>/g, '')
    .replace(/<parameter[\s\S]*?<\/parameter>/g, '')
    .replace(/<\/?(?:minimax|invoke|parameter|function_calls)[^>]*>/g, '');

  const codeFenceRegex = /```(\w*)\n?([\s\S]*?)```/g;
  const parts: Array<{ type: 'code'; code: string; lang: string } | { type: 'html'; html: string }> = [];
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
      key={version}
      className={variant === 'compact' ? 'text-[12px]' : 'text-[14px]'}
      style={{ lineHeight: '1.7' }}
    >
      {parts.map((part, i) => {
        if (part.type === 'code') {
          return <CodeBlock key={i} code={part.code} language={part.lang} />;
        }
        return (
          <div
            key={i}
            className="md-content"
            dangerouslySetInnerHTML={{ __html: parseInlineMarkdown(part.html) }}
          />
        );
      })}
    </div>
  );
}

export default memo(MarkdownRendererBase);
export { MarkdownRendererBase as MarkdownRenderer, CodeBlock, TerminalChrome, CollapsibleSection };
