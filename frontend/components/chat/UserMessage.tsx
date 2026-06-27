'use client';

import type { Message } from '@/types/chat';
import { MessageActionBar } from './MessageActionBar';

interface UserMessageProps {
  message: Message;
}

export default function UserMessage({ message }: UserMessageProps) {
  return (
    <div className="group flex justify-end">
      <div className="flex min-w-0 max-w-[82%] flex-col items-end">
        {message.attachments && message.attachments.length > 0 && (
          <div className="mb-1 flex flex-wrap gap-1.5 justify-end">
            {message.attachments.filter(a => a.isImage).map((a, i) => (
              <img
                key={i}
                src={a.data}
                alt={a.name}
                className="h-20 w-20 rounded-lg border object-cover"
                style={{ borderColor: 'var(--border)' }}
              />
            ))}
          </div>
        )}
        <div
          className="min-w-0 max-w-full px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap break-words"
          style={{
            background: 'var(--surface-user-msg)',
            color: 'var(--text)',
            borderRadius: '18px 4px 18px 18px',
            overflowWrap: 'anywhere',
            wordBreak: 'break-word',
          }}
        >
          {message.content}
        </div>
        <MessageActionBar
          text={message.content}
          timestamp={message.timestamp}
          align="end"
        />
      </div>
    </div>
  );
}
