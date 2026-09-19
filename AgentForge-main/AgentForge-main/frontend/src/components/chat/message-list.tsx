"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Bot, RotateCcw, User } from "lucide-react";
import { Button } from "@/components/ui/button";
import { markdownComponents } from "@/components/ui/markdown-components";
import { cn } from "@/lib/utils";
import type { ConversationMessageOut } from "@/lib/types";

export interface PendingMessage {
  clientId: string;
  content: string;
  status: "sending" | "sent" | "failed";
}

const NEAR_BOTTOM_THRESHOLD_PX = 120;
const REVEAL_MS_PER_CHUNK = 16;
const REVEAL_CHARS_PER_TICK = 3;

function isUser(role: string): boolean {
  return role === "human";
}

export function MessageList({
  messages,
  pending,
  onRetry,
  liveStatus,
}: {
  messages: ConversationMessageOut[];
  pending: PendingMessage[];
  onRetry: (clientId: string) => void;
  liveStatus?: string | null;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const isNearBottomRef = useRef(true);

  const [baselineCount] = useState(() => messages.length);
  const [animatedIndices, setAnimatedIndices] = useState<Set<number>>(() => new Set());
  const lastMessageIndex = messages.length - 1;
  const lastMessage = messages[lastMessageIndex];
  const shouldAnimateLast =
    lastMessage !== undefined &&
    !isUser(lastMessage.role) &&
    lastMessageIndex >= baselineCount &&
    !animatedIndices.has(lastMessageIndex);

  function handleScroll() {
    const element = scrollRef.current;
    if (!element) return;
    const distanceFromBottom = element.scrollHeight - element.scrollTop - element.clientHeight;
    isNearBottomRef.current = distanceFromBottom < NEAR_BOTTOM_THRESHOLD_PX;
  }

  function scrollToBottom(behavior: ScrollBehavior = "smooth") {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior });
  }

  useEffect(() => {
    scrollToBottom("auto");
  }, []);

  useEffect(() => {
    if (isNearBottomRef.current) scrollToBottom();
  }, [messages.length, pending.length, liveStatus]);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
    >
      {messages.length === 0 && pending.length === 0 && !liveStatus ? (
        <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-sm text-muted-foreground">
          <Bot className="size-6 opacity-50" />
          Send a message to continue this project.
        </div>
      ) : (
        <div className="space-y-4">
          {messages.map((message, index) => (
            <MessageBubble
              key={index}
              message={message}
              animate={index === lastMessageIndex && shouldAnimateLast}
              onAnimationDone={() =>
                setAnimatedIndices((current) => {
                  const next = new Set(current);
                  next.add(index);
                  return next;
                })
              }
              onRevealTick={() => {
                if (isNearBottomRef.current) scrollToBottom("auto");
              }}
            />
          ))}

          {pending.map((message) => (
            <PendingBubble key={message.clientId} message={message} onRetry={() => onRetry(message.clientId)} />
          ))}

          {liveStatus && (
            <div className="flex items-start gap-2.5">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary">
                <Bot className="size-3.5" />
              </span>
              <div className="flex items-center gap-2 rounded-xl bg-surface-2/60 px-3 py-2 text-sm text-muted-foreground">
                <span className="flex gap-0.5">
                  <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
                  <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
                  <span className="size-1.5 animate-bounce rounded-full bg-primary" />
                </span>
                {liveStatus}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PendingBubble({ message, onRetry }: { message: PendingMessage; onRetry: () => void }) {
  const failed = message.status === "failed";
  const sending = message.status === "sending";

  return (
    <div className="flex flex-row-reverse items-start gap-2.5">
      <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent text-foreground">
        <User className="size-3.5" />
      </span>
      <div className="flex max-w-[80%] flex-col items-end gap-1">
        <div
          className={cn(
            "rounded-xl px-3 py-2 text-sm text-foreground",
            failed ? "border border-status-failed/40 bg-status-failed/10" : "bg-primary/15",
            sending && "opacity-80",
          )}
        >
          {message.content}
        </div>
        {failed && (
          <Button size="xs" variant="outline" className="gap-1 text-status-failed" onClick={onRetry}>
            <RotateCcw className="size-3" />
            Retry
          </Button>
        )}
        {sending && <span className="text-[10px] text-muted-foreground">Sending…</span>}
      </div>
    </div>
  );
}

function MessageBubble({
  message,
  animate,
  onAnimationDone,
  onRevealTick,
}: {
  message: ConversationMessageOut;
  animate: boolean;
  onAnimationDone: () => void;
  onRevealTick: () => void;
}) {
  const userMessage = isUser(message.role);
  const [revealedLength, setRevealedLength] = useState(animate ? 0 : message.content.length);

  useEffect(() => {
    if (!animate) return;

    let revealed = 0;
    const interval = setInterval(() => {
      revealed = Math.min(revealed + REVEAL_CHARS_PER_TICK, message.content.length);
      setRevealedLength(revealed);
      onRevealTick();
      if (revealed >= message.content.length) {
        clearInterval(interval);
        onAnimationDone();
      }
    }, REVEAL_MS_PER_CHUNK);

    return () => clearInterval(interval);
  }, [animate]);

  const displayContent = animate ? message.content.slice(0, revealedLength) : message.content;
  const isRevealing = animate && revealedLength < message.content.length;

  return (
    <div className={cn("flex items-start gap-2.5", userMessage && "flex-row-reverse")}>
      <span
        className={cn(
          "flex size-6 shrink-0 items-center justify-center rounded-full",
          userMessage ? "bg-accent text-foreground" : "bg-primary/15 text-primary",
        )}
      >
        {userMessage ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
      </span>

      {userMessage ? (
        <div className="max-w-[80%] rounded-xl bg-primary/15 px-3 py-2 text-sm text-foreground">
          {message.content}
        </div>
      ) : (
        <article className="prose prose-invert prose-sm max-w-[80%] rounded-xl bg-surface-2/60 px-3 py-2 prose-pre:bg-surface prose-pre:border prose-pre:border-border/60 prose-code:text-primary prose-a:text-primary prose-p:my-1 first:prose-p:mt-0 last:prose-p:mb-0">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
            {displayContent}
          </ReactMarkdown>
          {isRevealing && (
            <span className="ml-0.5 inline-block h-3.5 w-1.5 animate-pulse bg-primary align-text-bottom" />
          )}
        </article>
      )}
    </div>
  );
}
