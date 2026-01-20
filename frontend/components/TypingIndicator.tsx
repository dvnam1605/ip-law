import React from 'react';

const TypingIndicator: React.FC = () => {
  return (
    <div className="flex space-x-1 items-center p-2 bg-gray-100 rounded-2xl rounded-tl-none w-fit">
      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.3s]"></div>
      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:-0.15s]"></div>
      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
    </div>
  );
};

export default TypingIndicator;