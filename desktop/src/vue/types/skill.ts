// P2-7 — SkillSource restricted to what backend actually produces
// (see madcop/server/routes/skills_routes.py). 'plugin'/'mcp'/'auto-distilled'
// were declared but never returned, so 'pluginName' became a dead field
// on SkillMeta (frontend used it, backend never supplied it).
export type SkillSource = 'user' | 'project' | 'bundled'

export type SkillMeta = {
  name: string
  displayName?: string
  description: string
  source: SkillSource
  userInvocable: boolean
  version?: string
  contentLength: number
  hasDirectory: boolean
}

export type FileTreeNode = {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileTreeNode[]
}

export type SkillFrontmatter = Record<string, unknown>

// P2-7 — frontmatter/body removed from SkillFile: backend never produces
// these fields, so any reader (SkillDetail.vue) saw undefined. 'path',
// 'content', 'language', 'isEntry' are the real contract.
export type SkillFile = {
  path: string
  content: string
  language: string
  isEntry?: boolean
}

export type SkillDetail = {
  meta: SkillMeta
  tree: FileTreeNode[]
  files: SkillFile[]
  skillRoot: string
}