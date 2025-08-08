import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
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
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex]}
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
          h1: ({ children }) => {
            const text = String(children);
            const { difficulty, topics } = extractMetadata(text);
            
            return (
              <div className="section-divider first:mt-0 first:pt-0">
                <h1 className="display-h1 mb-6">
                  {children}
                </h1>
                {(difficulty || topics) && (
                  <div className="flex flex-wrap gap-2 mb-8">
                    {difficulty && (
                      <span className="chip-warn">
                        Difficulty: {difficulty}
                      </span>
                    )}
                    {topics?.map((topic, idx) => (
                      <span key={idx} className="chip-info">
                        {topic}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          },
          h2: ({ children }) => {
            const text = String(children);
            const isQuestion = isQuestionHeading(text);
            const { difficulty, topics } = extractMetadata(text);
            
            if (isQuestion) {
              return (
                <div className="card-base p-7 my-10 animate-fade-in">
                  <div className="flex items-start justify-between mb-5">
                    <h2 className="display-h2 flex-1">
                      {children}
                    </h2>
                    {difficulty && (
                      <span className="chip-warn ml-4">
                        {difficulty}
                      </span>
                    )}
                  </div>
                  {topics && topics.length > 0 && (
                    <div className="flex flex-wrap gap-3">
                      {topics.map((topic, idx) => (
                        <span key={idx} className="chip-info">
                          {topic}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            }
            
            return (
              <h2 className="display-h2 section-divider">
                {children}
              </h2>
            );
          },
          h3: ({ children }) => (
            <h3 className="display-h3 mb-5">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="body-default mb-6 leading-relaxed">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="mb-8 pl-6 space-y-3 body-default list-disc">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-8 pl-6 space-y-3 body-default list-decimal">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="relative leading-relaxed">
              {children}
            </li>
          ),
          blockquote: ({ children }) => (
            <div className="card-base p-5 my-8 border-l-4 border-primary bg-primary/5">
              <div className="body-default">
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
            <th className="px-4 py-3 text-left caption-text font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-4 py-3 body-default">
              {children}
            </td>
          ),
          hr: () => (
            <div className="divider-horizontal my-8" />
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
};