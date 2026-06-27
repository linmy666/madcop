'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';
import hljs from 'highlight.js/lib/common';
import { Check, Copy } from 'lucide-react';

// ── marked config ──────────────────────────────────────────────
marked.setOptions({
  gfm: true,
  breaks: true,
});

/** Strip model-specific pseudo-tags before parsing. */
function stripModelTags(md: string): string {
  return md
    .replace(/<\/?minimax:tool_call>/gi, '')
    .replace(/<\/?(?:tool|function):(?:call|result|args)>/gi, '')
    .replace(/<\|im_start\|>|<\|im_end\|>/gi, '');
}

// ── CodeBlock with copy + language label ───────────────────────
function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false);
  const langLabel = lang || 'text';

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }, [code]);

  let highlighted: string;
  try {
    highlighted =
      lang && hljs.getLanguage(lang)
        ? hljs.highlight(code, { language: lang }).value
        : hljs.highlightAuto(code).value;
  } catch {
    highlighted = code;
  }

  return (
    <div className="group/code relative my-3 overflow-hidden rounded-lg border border-[var(--border)]"
      style={{ background: 'var(--code-bg)' }}>
      <div className="flex items-center justify-between px-3 py-1.5 text-xs"
        style={{ background: 'var(--surface-2)', borderBottom: '1px solid var(--border)' }}>
        <span className="font-mono text-[var(--text-3)]">{langLabel}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 text-[var(--text-3)] transition-colors hover:text-[var(--text)]"
        >
          {copied ? <Check size={13} /> : <Copy size={13} />}
          {copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre className="overflow-x-auto p-3 text-[13px] leading-relaxed">
        <code
          className="hljs font-mono"
          style={{ color: 'var(--code-fg)' }}
          dangerouslySetInnerHTML={{ __html: highlighted }}
        />
      </pre>
    </div>
  );
}

// ── Inline code ────────────────────────────────────────────────
function InlineCode({ code }: { code: string }) {
  return (
    <code
      className="rounded px-1.5 py-0.5 text-[13px] font-mono"
      style={{
        background: 'var(--code-bg)',
        color: 'var(--code-fg)',
      }}
    >
      {code}
    </code>
  );
}

// ── Main renderer ──────────────────────────────────────────────
export default function MarkdownRenderer({ content }: { content: string }) {
  const [html, setHtml] = useState('');
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!content) {
      setHtml('');
      return;
    }

    const cleaned = stripModelTags(content);
    const raw = marked.parse(cleaned, { async: false }) as string;

    // Build a DOM so we can extract fenced code blocks for custom rendering.
    const wrapper = document.createElement('div');
    wrapper.innerHTML = DOMPurify.sanitize(raw, {
      ADD_ATTR: ['target', 'rel'],
    });

    // Process <pre><code> blocks: save to data attr for React extraction
    wrapper.querySelectorAll('pre code').forEach((el) => {
      const codeEl = el as HTMLElement;
      const lang =
        codeEl.className.match(/language-(\w+)/)?.[1] || '';
      const code = codeEl.textContent || '';
      const pre = codeEl.closest('pre');
      if (pre) {
        // Replace <pre> with a placeholder we'll find later
        const placeholder = document.createElement('div');
        placeholder.setAttribute('data-codeblock', '1');
        placeholder.setAttribute('data-lang', lang);
      }
    });

    setHtml(wrapper.innerHTML);
  }, [content]);

  return (
    <div
      ref={containerRef}
      className="markdown-body text-[14px] leading-7 text-[var(--text)] [&_a]:text-[var(--accent)] [&_a:hover]:underline [&_blockquote]:border-l-2 [&_blockquote]:border-[var(--accent)] [&_blockquote]:pl-3 [&_blockquote]:text-[var(--text-2)] [&_h1]:mb-3 [&_h1]:mt-4 [&_h1]:text-xl [&_h1]:font-bold [&_h2]:mb-2 [&_h2]:mt-3 [&_h2]:text-lg [&_h2]:font-bold [&_h3]:mb-2 [&_h3]:mt-2 [&_h3]:text-base [&_h3]:font-semibold [&_img]:max-w-full [&_img]:rounded-lg [&_li]:ml-5 [&_li]:list-disc [&_ol]:ml-5 [&_ol]:list-decimal [&_p]:my-2 [&_table]:w-full [&_table]:border-collapse [&_th]:border [&_th]:border-[var(--border)] [&_th]:px-3 [&_th]:py-1.5 [&_th]:text-left [&_th]:font-semibold [&_td]:border [&_td]:border-[var(--border)] [&_td]:px-3 [&_td]:py-1.5 [&_ul]:my-1.5"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
