export function shouldSubmitOnEnter(event: any, behavior: any): boolean {
  return event.key === 'Enter' && !event.shiftKey
}