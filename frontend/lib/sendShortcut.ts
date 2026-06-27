/**
 * Keyboard send behavior config.
 * - 'enter': Enter sends, Shift+Enter for newline (default, like ChatGPT)
 * - 'modifierEnter': Cmd/Ctrl+Enter sends, Enter for newline (like Slack)
 */
export type SendBehavior = 'enter' | 'modifierEnter';

export function shouldSubmitOnEnter(
  event: { key: string; shiftKey: boolean; ctrlKey: boolean; metaKey: boolean },
  behavior: SendBehavior = 'enter',
): boolean {
  if (event.key !== 'Enter' || event.shiftKey) return false;
  if (behavior === 'modifierEnter') return event.ctrlKey || event.metaKey;
  return !event.ctrlKey && !event.metaKey;
}
