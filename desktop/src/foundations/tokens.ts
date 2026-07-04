// MadCop Foundations: the source of truth for the visual system.
//
// Why a TS file and not a CSS file: every other layer of the app
// imports its design tokens from here, so we cannot drift between
// the design (in TS) and the rendering (in CSS).
//
// Naming convention: `madcop.<role>.<variant>`
//   role:   color  | type  | space | radius | shadow | motion
//   variant: e.g. `blue/9` for OKLCH-style scale, or `panel/2` for the panel scale.
//
// Deliberate non-affinity with Material You: this is NOT another
// Material Design 3 clone. The look is industrial / engineering:
//   - Cooler hues (cyan/blue), warm accents reserved for status
//   - Square corners (6/10/14), 1.5px hairlines, minimal shadow
//   - Mono numerics, ASCII system icons, no Material Symbols

// ── 1. Color ───────────────────────────────────────────────────────── //
//
// Each scale is 12 steps: 0 = background-tinted, 6 = baseline, 12 = high-contrast.
// OKLCH-style steps inspired by Radix / Geist, not Material 3.
// Cyan is the brand, amber is status, jade is success, vermilion is danger.

export const color = {
  // Cool brand (cyan-700 family)
  blue: {
    0:  '#F0F9FB',
    1:  '#E1F4F8',
    2:  '#C2E9F0',
    3:  '#8FD4E0',
    4:  '#5DBED0',
    5:  '#2EA6BC',
    6:  '#0E7490',  // brand
    7:  '#0C627A',
    8:  '#0A5165',
    9:  '#08404F',
    10: '#052F3A',
    11: '#031E25',
    12: '#010E11',
  },
  // Warm status (amber for warnings / commit indicators)
  amber: {
    0:  '#FEF8EB',
    1:  '#FCF0D2',
    2:  '#F8DDA0',
    3:  '#F5CB6F',
    4:  '#F0B83D',
    5:  '#D49A1F',
    6:  '#B45309',  // status
    7:  '#8E4206',
    8:  '#683104',
    9:  '#432002',
    10: '#1F0F01',
    11: '#0A0400',
    12: '#000000',
  },
  // Success (jade — desaturated, not material's grass)
  jade: {
    0:  '#ECFDF5',
    1:  '#D1FAE5',
    2:  '#A7F3D0',
    3:  '#6EE7B7',
    4:  '#34D399',
    5:  '#10B981',
    6:  '#059669',  // success
    7:  '#047857',
    8:  '#065F46',
    9:  '#064E3B',
    10: '#022C22',
    11: '#011A14',
    12: '#000A07',
  },
  // Danger (vermilion — slightly desaturated, cargo-warn feel)
  vermilion: {
    0:  '#FEF2F2',
    1:  '#FEE2E2',
    2:  '#FECACA',
    3:  '#FCA5A5',
    4:  '#F87171',
    5:  '#EF4444',
    6:  '#DC2626',  // danger
    7:  '#B91C1C',
    8:  '#991B1B',
    9:  '#7F1D1D',
    10: '#450A0A',
    11: '#260505',
    12: '#0A0000',
  },
  // Neutral (slate-cyan — cooler than pure gray)
  slate: {
    0:  '#F8FAFC',
    1:  '#F1F5F9',
    2:  '#E2E8F0',
    3:  '#CBD5E1',
    4:  '#94A3B8',
    5:  '#64748B',
    6:  '#475569',  // text-body
    7:  '#334155',
    8:  '#1E293B',
    9:  '#0F172A',  // text-strong
    10: '#0B1220',
    11: '#070C16',
    12: '#03060C',
  },
} as const

// Semantic roles (refer to the above scales; never hardcode hex in components).
// Light theme by default; dark variant inverts blue-12 / slate-12 / etc.
export const semantic = {
  light: {
    // surfaces
    panel:           color.slate[0],   // app body bg
    panelRaised:     color.slate[1],   // cards
    panelSunken:     color.slate[2],   // input wells
    overlay:         'rgba(15, 23, 42, 0.36)',  // modal scrim
    glass:           'rgba(255, 255, 255, 0.78)',  // floating toolbars
    glassLine:       'rgba(15, 23, 42, 0.10)',

    // ink
    ink:             color.slate[9],   // strongest text
    inkBody:         color.slate[6],   // body text
    inkMuted:        color.slate[5],   // captions / labels
    inkSubtle:       color.slate[4],   // hints
    inkInvert:       color.slate[0],   // on dark surfaces

    // line
    line:            color.slate[3],   // 1.5px borders
    lineStrong:      color.slate[4],   // stronger divider
    lineFocus:       color.blue[6],

    // accent (brand)
    accent:          color.blue[6],
    accentHover:     color.blue[7],
    accentActive:    color.blue[8],
    accentSubtle:    color.blue[2],
    accentInk:       color.slate[0],   // text on accent

    // status
    success:         color.jade[6],
    successSubtle:   color.jade[1],
    warn:            color.amber[6],
    warnSubtle:      color.amber[1],
    danger:          color.vermilion[6],
    dangerSubtle:    color.vermilion[1],

    // accent edge — the 3px highlight rail on the active sidebar item
    accentRail:      color.blue[6],

    // grid pattern (the barely-there engineering blueprint)
    grid:            `rgba(15, 23, 42, 0.04)`,
  },
  dark: {
    panel:           color.slate[11],
    panelRaised:     color.slate[10],
    panelSunken:     color.slate[12],
    overlay:         'rgba(0, 0, 0, 0.6)',
    glass:           'rgba(15, 23, 42, 0.78)',
    glassLine:       'rgba(255, 255, 255, 0.08)',

    ink:             color.slate[0],
    inkBody:         color.slate[3],
    inkMuted:        color.slate[4],
    inkSubtle:       color.slate[5],
    inkInvert:       color.slate[9],

    line:            color.slate[8],
    lineStrong:      color.slate[7],
    lineFocus:       color.blue[4],

    accent:          color.blue[5],
    accentHover:     color.blue[4],
    accentActive:    color.blue[3],
    accentSubtle:    color.blue[9],
    accentInk:       color.slate[12],

    success:         color.jade[4],
    successSubtle:   color.jade[9],
    warn:            color.amber[4],
    warnSubtle:      color.amber[9],
    danger:          color.vermilion[4],
    dangerSubtle:    color.vermilion[9],

    accentRail:      color.blue[5],

    grid:            'rgba(255, 255, 255, 0.04)',
  },
} as const

// ── 2. Type ────────────────────────────────────────────────────────── //
//
// Inter for UI, Geist Mono for code/numbers. Both self-hosted WOFF2 (see globals.css).
// NOT Manrope — different proportions, sharper corners.

export const type = {
  // sizes
  size: {
    micro:  '11px',
    caption:'12px',
    body:   '13px',
    base:   '14px',
    lead:   '15px',
    h3:     '16px',
    h2:     '20px',
    h1:     '26px',
    display:'32px',
    banner: '48px',
  },
  // weights
  weight: {
    regular:   400,
    medium:    500,
    semibold:  600,
    bold:      700,
  },
  // line heights
  leading: {
    tight:   1.2,
    snug:    1.35,
    normal:  1.5,
    relaxed: 1.65,
  },
  // families
  family: {
    ui:    'Inter, system-ui, sans-serif',
    mono:  'Geist Mono, JetBrains Mono, Menlo, monospace',
    display: 'Inter, system-ui, sans-serif',  // no separate display face
  },
  // letter-spacing
  tracking: {
    tight:   '-0.01em',
    normal:  '0',
    wide:    '0.02em',
    banner:  '-0.025em',
  },
  // small-caps for labels (engineering CAD style)
  eyebrow: {
    transform: 'uppercase',
    weight:    600,
    tracking:  '0.08em',
    size:      '11px',
  } as const,
} as const

// ── 3. Space ───────────────────────────────────────────────────────── //
// 4px base, geometric scale up to 80px (no quirky values).

export const space = {
  '0':  '0',
  '0.5':'2px',
  '1':  '4px',
  '1.5':'6px',
  '2':  '8px',
  '2.5':'10px',
  '3':  '12px',
  '4':  '16px',
  '5':  '20px',
  '6':  '24px',
  '7':  '28px',
  '8':  '32px',
  '10': '40px',
  '12': '48px',
  '16': '64px',
  '20': '80px',
} as const

// ── 4. Radius ──────────────────────────────────────────────────────── //
// Harder than Material You (6/10/14 not 8/12/16). Intentional.

export const radius = {
  none:  '0',
  hair:  '2px',
  edge:  '6px',     // buttons, inputs
  card:  '8px',     // cards, panels
  panel: '10px',    // modals, sheets
  ribbon:'14px',    // hero surfaces
  pill:  '9999px',
} as const

// ── 5. Stroke ──────────────────────────────────────────────────────── //
// Borders before shadows. Most borders are 1.5px — feels more solid
// than the 1px norm without becoming a Windows 95 outline.

export const stroke = {
  hair:  '1px',
  edge:  '1.5px',
  bold:  '2px',
  rail:  '3px',  // sidebar active accent
} as const

// ── 6. Shadow ──────────────────────────────────────────────────────── //
// One flat shadow only — no double-stacked glow. We prefer hairline
// borders over layered shadows (engineering, not material).

export const shadow = {
  none:  'none',
  hair:  '0 0 0 1px rgba(15, 23, 42, 0.06)',
  panel: '0 1px 0 rgba(15, 23, 42, 0.04), 0 0 0 1px rgba(15, 23, 42, 0.04)',
  raised:'0 1px 2px rgba(15, 23, 42, 0.08), 0 0 0 1px rgba(15, 23, 42, 0.04)',
  pop:   '0 8px 24px rgba(15, 23, 42, 0.12), 0 0 0 1px rgba(15, 23, 42, 0.04)',
  modal: '0 16px 48px rgba(15, 23, 42, 0.18), 0 0 0 1px rgba(15, 23, 42, 0.04)',
  focus: '0 0 0 2px rgba(14, 116, 144, 0.32)',
  ring:  '0 0 0 3px rgba(14, 116, 144, 0.18)',
} as const

// ── 7. Motion ──────────────────────────────────────────────────────── //
// Slightly faster than material's 200ms — software tools feel snappy.

export const motion = {
  duration: {
    instant:  '0ms',
    fast:     '80ms',
    base:     '140ms',
    smooth:   '220ms',
    slow:     '320ms',
  },
  easing: {
    standard: 'cubic-bezier(0.2, 0, 0, 1)',     // out
    enter:    'cubic-bezier(0, 0, 0.2, 1)',       // decel
    exit:     'cubic-bezier(0.4, 0, 1, 1)',       // accel
    spring:   'cubic-bezier(0.34, 1.56, 0.64, 1)',
  },
} as const

// ── 8. Layout dimensions ───────────────────────────────────────────── //
// Tighter than the previous shell. Titlebar is shorter, sidebar is
// narrower, more room for content.

export const layout = {
  titlebarHeight:  32,  // was 40
  statusbarHeight: 28,  // was 36
  sidebarWidth:    240, // was 280
  sidebarCollapsed: 52, // was 72
  tabstripHeight:  36,  // was 44
  contentMaxWidth: 1080,
} as const

// ── 9. Z-index ladder ──────────────────────────────────────────────── //

export const z = {
  base:    0,
  raised:  10,
  sticky:  100,
  overlay: 1000,
  modal:   1100,
  toast:   2000,
  dev:     9999,
} as const

// ── 10. ASCII system icons (no Material Symbols) ─────────────────── //
//
// We're replacing the icon set entirely. The shell used to call
// `material-symbols-outlined` for everything. Now we ship an inline
// SVG set + a tiny set of ASCII glyphs for the most-used places
// (sidebar nav, status pills). Code points are deliberately chosen
// to be glyphs that exist in every monospace + UI font.

export const icon = {
  // Sidebar / nav
  chat:       '◇',     // empty diamond = "new"
  threads:    '◫',     // half-filled rectangle = threads
  skills:     '◐',     // half circle = skills
  memory:     '◉',     // filled target = memory
  find:       '⌕',     // search
  agent:      '◈',     // diamond with dot = agent
  workflow:   '⬡',     // hexagon = workflow
  design:     '◰',     // squared = design
  trace:      '∿',     // wavy = trace
  teams:      '⏣',     // team
  doctor:     '✚',     // plus = doctor
  settings:   '⚙',     // settings
  terminal:   '▣',     // terminal
  browser:    '◯',     // browser
  activity:   '◭',     // activity
  schedule:   '◷',     // schedule
  diagnostics:'◔',     // diagnostics
  adapter:    '⇄',     // adapter

  // Directional / state
  arrow: {
    up:    '↑',
    down:  '↓',
    left:  '←',
    right: '→',
  },
  close:  '×',
  add:    '+',
  check:  '✓',
  dot:    '·',
  bullet: '•',
  empty:  '∅',
  warn:   '!',
  magnify:'⌕',
} as const

// ── 11. Default export = the whole system ─────────────────────────── //

export const madcop = {
  color,
  semantic,
  type,
  space,
  radius,
  stroke,
  shadow,
  motion,
  layout,
  z,
  icon,
} as const

export type MadcopTokens = typeof madcop
export type SemanticTokens = typeof semantic.light
