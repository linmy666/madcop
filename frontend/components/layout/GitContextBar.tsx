'use client';

import { GitBranch, GitCommit, ChevronDown, FolderGit2, Plus } from 'lucide-react';
import { useState } from 'react';

interface Props {
  /** Repository display name (e.g. "NanmiCoder/cc-haha") */
  repo?: string;
  /** Current branch name (e.g. "main") */
  branch?: string;
  /** Git status description (e.g. "当前工作树" / "clean" / "3 modified") */
  status?: string;
  /** Number of changes shown in the side panel */
  changeCount?: number;
  /** Click to open the worktree dropdown */
  onClick?: () => void;
}

/**
 * Git context bar — sits below the composer and shows
 * the repo / branch / git status. Pattern from production agent UIs.
 */
export function GitContextBar({
  repo = 'MadCop-Agent/frontend',
  branch = 'main',
  status = 'Clean working tree',
  changeCount = 0,
  onClick,
}: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div
      className="mx-auto max-w-3xl px-4 pb-1 flex items-center gap-1.5 text-[11px]"
      style={{ color: 'var(--text-3)' }}
    >
      {/* Repo + branch */}
      <button
        onClick={onClick}
        className="flex items-center gap-1.5 px-2 py-0.5 rounded transition-colors hover:bg-[var(--surface-hover)]"
      >
        <FolderGit2 size={11} style={{ color: 'var(--accent)' }} />
        <span className="font-medium">{repo}</span>
        <span style={{ color: 'var(--text-faint)' }}>·</span>
        <GitBranch size={11} />
        <span>{branch}</span>
        <ChevronDown size={9} />
      </button>

      {/* Status */}
      <span className="flex-1 truncate" style={{ color: 'var(--text-faint)' }}>
        {status}
      </span>

      {/* Changes count */}
      {changeCount > 0 && (
        <button
          className="flex items-center gap-1 px-1.5 py-0.5 rounded transition-colors hover:bg-[var(--surface-hover)]"
          style={{ color: 'var(--text-2)' }}
        >
          <GitCommit size={11} />
          <span>+{changeCount}</span>
        </button>
      )}

      {/* New chat button (right side) */}
      <button
        className="h-5 w-5 flex items-center justify-center rounded transition-colors hover:bg-[var(--surface-hover)]"
        style={{ color: 'var(--text-3)' }}
        title="New session"
      >
        <Plus size={11} />
      </button>
    </div>
  );
}
