/** Vue-side re-export of the real desktop host bridge.
 * Historically this was a stub exposing only `isDesktop`, which silently broke
 * every caller that touched `host.capabilities` / `host.notifications` / `host.zoom`
 * (undefined on the stub → runtime TypeError). The real host lives in
 * `src/lib/desktopHost/` (electron preload injects `window.desktopHost`), so this
 * module now just re-exports it — all `./desktopHost` importers inside vue/lib
 * get the full bridge. */
export * from '../../lib/desktopHost'

declare global {
  interface Window {
    electronApi?: unknown
    madcopDesktop?: unknown
    desktopHost?: unknown
  }
}
