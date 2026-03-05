import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import { Message } from '../types';
import { User, Bot, AlertCircle, Copy, BookOpen, Scale, Layers } from 'lucide-react';

interface MessageBubbleProps {
  message: Message;
}

// Markdown renderer with proper styling for tables, code blocks, etc.
const MarkdownContent: React.FC<{ content: string }> = ({ content }) => {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeRaw]}
      components={{
        // Code blocks
        code({ node, inline, className, children, ...props }: any) {
          const match = /language-(\w+)/.exec(className || '');
          const codeContent = String(children).replace(/\n$/, '');

          if (!inline && match) {
            return (
              <div className="relative group my-3 rounded-lg overflow-hidden border border-gray-700 bg-gray-950">
                <div className="flex justify-between items-center px-4 py-2 bg-gray-900 border-b border-gray-800 text-xs text-gray-400 font-mono">
                  <span>{match[1]}</span>
                  <button
                    onClick={() => navigator.clipboard.writeText(codeContent)}
                    className="hover:text-white flex items-center gap-1 transition-colors"
                  >
                    <Copy size={12} /> Copy
                  </button>
                </div>
                <pre className="!m-0 !bg-transparent text-sm overflow-x-auto text-gray-300 !border-0 p-4">
                  <code>{codeContent}</code>
                </pre>
              </div>
            );
          } else if (!inline) {
            return (
              <div className="relative group my-3 rounded-lg overflow-hidden border border-gray-700 bg-gray-950">
                <div className="flex justify-between items-center px-4 py-2 bg-gray-900 border-b border-gray-800 text-xs text-gray-400 font-mono">
                  <span>text</span>
                  <button
                    onClick={() => navigator.clipboard.writeText(codeContent)}
                    className="hover:text-white flex items-center gap-1 transition-colors"
                  >
                    <Copy size={12} /> Copy
                  </button>
                </div>
                <pre className="!m-0 !bg-transparent text-sm overflow-x-auto text-gray-300 !border-0 p-4">
                  <code>{codeContent}</code>
                </pre>
              </div>
            );
          }
          return (
            <code className="bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-200 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
              {children}
            </code>
          );
        },
        // Tables
        table({ children }) {
          return (
            <div className="overflow-x-auto my-4">
              <table className="min-w-full border-collapse border border-gray-300 dark:border-gray-700 rounded-lg overflow-hidden">
                {children}
              </table>
            </div>
          );
        },
        thead({ children }) {
          return <thead className="bg-gray-100 dark:bg-gray-800">{children}</thead>;
        },
        tbody({ children }) {
          return <tbody className="divide-y divide-gray-200 dark:divide-gray-700">{children}</tbody>;
        },
        tr({ children }) {
          return <tr className="hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors">{children}</tr>;
        },
        th({ children }) {
          return (
            <th className="px-4 py-3 text-left text-sm font-semibold text-gray-700 dark:text-gray-300 border-b border-gray-300 dark:border-gray-700">
              {children}
            </th>
          );
        },
        td({ children }) {
          return (
            <td className="px-4 py-3 text-sm text-gray-600 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
              {children}
            </td>
          );
        },
        // Headers
        h1({ children }) {
          return <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mt-6 mb-3">{children}</h1>;
        },
        h2({ children }) {
          return <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100 mt-5 mb-2">{children}</h2>;
        },
        h3({ children }) {
          return <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-200 mt-4 mb-2">{children}</h3>;
        },
        // Lists
        ul({ children }) {
          return <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>;
        },
        ol({ children }) {
          return <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>;
        },
        li({ children }) {
          return <li className="text-gray-700 dark:text-gray-300 pl-1">{children}</li>;
        },
        // Paragraphs
        p({ children }) {
          return <p className="my-2 leading-7">{children}</p>;
        },
        // Bold and italic
        strong({ children }) {
          return <strong className="font-semibold text-gray-900 dark:text-gray-100">{children}</strong>;
        },
        em({ children }) {
          return <em className="italic">{children}</em>;
        },
        // Links
        a({ href, children }) {
          return (
            <a href={href} className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 underline" target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          );
        },
        // Blockquotes
        blockquote({ children }) {
          return (
            <blockquote className="border-l-4 border-gray-300 dark:border-gray-600 pl-4 my-3 italic text-gray-600 dark:text-gray-400">
              {children}
            </blockquote>
          );
        },
        // Horizontal rule
        hr() {
          return <hr className="my-4 border-gray-300 dark:border-gray-700" />;
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
};

const routeLabels: Record<string, { label: string; icon: React.ReactNode; color: string }> = {
  legal: { label: 'Văn bản pháp luật', icon: <BookOpen className="w-3 h-3" />, color: 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 border-blue-100 dark:border-blue-800' },
  verdict: { label: 'Bản án', icon: <Scale className="w-3 h-3" />, color: 'bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 border-amber-100 dark:border-amber-800' },
  combined: { label: 'Tổng hợp', icon: <Layers className="w-3 h-3" />, color: 'bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 border-purple-100 dark:border-purple-800' },
};

const MessageBubble: React.FC<MessageBubbleProps> = ({ message }) => {
  const isUser = message.role === 'user';
  const isError = message.isError;
  const route = message.routeType ? routeLabels[message.routeType] : null;

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} mb-8 group animate-in fade-in slide-in-from-bottom-2 duration-300`}>
      <div className={`flex max-w-[90%] md:max-w-[80%] lg:max-w-[70%] ${isUser ? 'flex-row-reverse' : 'flex-row'} gap-4 items-start`}>

        {/* Avatar */}
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center shadow-sm border ${isUser ? 'bg-black dark:bg-white border-black dark:border-white' : isError ? 'bg-red-500 border-red-500' : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
          }`}>
          {isUser ? (
            <User className="w-4 h-4 text-white dark:text-black" />
          ) : isError ? (
            <AlertCircle className="w-4 h-4 text-white" />
          ) : (
            <Bot className="w-4 h-4 text-black dark:text-gray-300" />
          )}
        </div>

        {/* Bubble Content */}
        <div
          className={`flex-1 min-w-0 ${isUser
            ? 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100 rounded-2xl rounded-tr-sm px-6 py-4'
            : isError
              ? 'bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 border border-red-100 dark:border-red-800 rounded-2xl rounded-tl-sm px-6 py-4'
              : 'text-gray-900 dark:text-gray-100 pt-1'
            }`}
        >
          {isUser ? (
            <div className="whitespace-pre-wrap text-sm md:text-base leading-relaxed font-medium">{message.content}</div>
          ) : (
            <div className="text-sm md:text-base leading-7 font-light text-gray-800 dark:text-gray-200">
              {route && (
                <div className="mb-2">
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${route.color}`}>
                    {route.icon}
                    {route.label}
                  </span>
                </div>
              )}
              {isError ? message.content : <MarkdownContent content={message.content} />}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default MessageBubble;