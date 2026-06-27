'use client';

import type { Message } from '@/types/chat';
import { MessageActionBar } from './MessageActionBar';

interface Props {
  message: Message;
}

export default function UserMessage({ message }: Props) {
  return (
    <div className="group flex justify-end">
      <div
        data-message-shell="user"
        className="flex min-w-0 max-w-[78%] flex-col items-end"
      >
        {message.attachments && message.attachments.length > 0 && (
          <div className="mb-1.5 flex flex-wrap gap-1.5 justify-end">
            {message.attachments
              .filter((a) => a.isImage)
              .map((a, i) => (
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
          className="min-w-0 max-w-full px-3.5 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap break-words"
          style={{
            background: 'var(--surface-user)',
            color: 'var(--text)',
            borderRadius: '18px 4px 18px 18px',
            overflowWrap: 'anywhere',
            wordBreak: 'break-word',
            boxShadow: 'var(--shadow-sm)',
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
