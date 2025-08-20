import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';
import rehypeRaw from 'rehype-raw';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { useTheme } from '../hooks/useTheme';

interface MarkdownViewerProps {
  content: string;
  className?: string;
}

export const MarkdownViewer: React.FC<MarkdownViewerProps> = ({ 
  content, 
  className = '' 
}) => {
  const { isDark } = useTheme();

  // Helper function to detect question patterns
  const isQuestionHeading = (text: string) => {
    const questionWords = ['Question', 'Task', 'Problem', 'Exercise', 'Q:', 'Вопрос', 'Задача', 'Задание'];
    return questionWords.some(word => text.includes(word)) || /^\d+\./.test(text);
  };

  // Helper function to extract difficulty and topics from content
  const extractMetadata = (text: string) => {
    const difficulty = text.match(/(?:сложность|difficulty):\s*([^\n]+)/i)?.[1]?.trim();
    const topics = text.match(/(?:темы|topics):\s*([^\n]+)/i)?.[1]?.split(',').map(t => t.trim());
    return { difficulty, topics };
  };

  return (
    <div className={`prose max-w-none space-y-8 ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath, remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeKatex]}
        components={{
          code({ node, inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            
            if (!inline && match) {
              return (
                <SyntaxHighlighter
                  style={isDark ? oneDark : oneLight}
                  language={match[1]}
                  PreTag="div"
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              );
            }

            return (
              <code 
                className="bg-elev border border-border px-1.5 py-0.5 rounded text-xs font-mono"
                {...props}
              >
                {children}
              </code>
            );
          },
          h1: ({ children }) => (
            <h1 style={{ fontSize: '2rem', fontWeight: 'bold', marginBottom: '1.5rem', marginTop: '2rem' }}>
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 style={{ fontSize: '1.75rem', fontWeight: '600', marginBottom: '1.25rem', marginTop: '1.75rem' }}>
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 style={{ fontSize: '1.375rem', fontWeight: '600', marginBottom: '1rem', marginTop: '1.5rem' }}>
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="text-lg mb-6 leading-relaxed">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="mb-8 pl-6 space-y-3 text-lg list-disc">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-8 pl-6 space-y-3 text-lg list-decimal">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="relative leading-relaxed">
              {children}
            </li>
          ),
          blockquote: ({ children }) => (
            <div className="pl-6 my-8 border-l-4 border-primary">
              <div className="text-lg italic opacity-90">
                {children}
              </div>
            </div>
          ),
          a: ({ href, children }) => (
            <a 
              href={href} 
              className="text-primary hover:brightness-110 underline underline-offset-2 transition-all duration-120"
              target="_blank"
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto mb-8">
              <div className="card-base">
                <table className="w-full">
                  {children}
                </table>
              </div>
            </div>
          ),
          thead: ({ children }) => (
            <thead className="card-header">
              {children}
            </thead>
          ),
          tbody: ({ children }) => (
            <tbody className="divide-y divide-border/60">
              {children}
            </tbody>
          ),
          th: ({ children }) => (
            <th className="px-4 py-3 text-left font-semibold" style={{ fontSize: '1.125rem' }}>
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-4 py-3 text-base align-top" style={{ whiteSpace: 'pre-wrap' }}>
              {children}
            </td>
          ),
          hr: () => null,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};