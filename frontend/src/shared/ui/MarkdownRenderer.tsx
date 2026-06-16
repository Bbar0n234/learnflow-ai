import { Streamdown } from "streamdown";
import { code } from "@streamdown/code";
import { createMathPlugin } from "@streamdown/math";

const math = createMathPlugin({ singleDollarTextMath: true });
import { mermaid } from "@streamdown/mermaid";

interface MarkdownRendererProps {
  children: string;
  isStreaming?: boolean;
}

export function MarkdownRenderer({
  children,
  isStreaming,
}: MarkdownRendererProps) {
  return (
    <Streamdown
      plugins={{ code, math, mermaid }}
      mode={isStreaming ? "streaming" : "static"}
      animated={isStreaming}
      isAnimating={isStreaming}
    >
      {children}
    </Streamdown>
  );
}
