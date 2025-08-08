import React, { useState } from 'react';
import { ChevronDown, ChevronRight, BookOpen, Target, Clock, CheckCircle } from 'lucide-react';

export interface QuestionData {
  id: string;
  title: string;
  content: string;
  answer?: string;
  difficulty?: 'easy' | 'medium' | 'hard';
  topics?: string[];
  type?: 'multiple-choice' | 'open-ended' | 'true-false';
  points?: number;
  timeEstimate?: number; // minutes
  isCompleted?: boolean;
}

interface QuestionCardProps {
  question: QuestionData;
  showAnswer?: boolean;
  isExpanded?: boolean;
  onToggleExpanded?: (expanded: boolean) => void;
  onMarkComplete?: (questionId: string, completed: boolean) => void;
  className?: string;
}

export const QuestionCard: React.FC<QuestionCardProps> = ({
  question,
  showAnswer = false,
  isExpanded: controlledExpanded,
  onToggleExpanded,
  onMarkComplete,
  className = ''
}) => {
  const [internalExpanded, setInternalExpanded] = useState(false);
  
  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;
  
  const handleToggleExpanded = () => {
    const newExpanded = !isExpanded;
    if (onToggleExpanded) {
      onToggleExpanded(newExpanded);
    } else {
      setInternalExpanded(newExpanded);
    }
  };

  const handleMarkComplete = () => {
    if (onMarkComplete) {
      onMarkComplete(question.id, !question.isCompleted);
    }
  };

  const getDifficultyChip = (difficulty?: string) => {
    switch (difficulty) {
      case 'easy':
        return <span className="chip-success">Easy</span>;
      case 'medium':
        return <span className="chip-warn">Medium</span>;
      case 'hard':
        return <span className="chip-danger">Hard</span>;
      default:
        return null;
    }
  };

  const getTypeIcon = (type?: string) => {
    switch (type) {
      case 'multiple-choice':
        return <Target className="w-4 h-4" />;
      case 'open-ended':
        return <BookOpen className="w-4 h-4" />;
      default:
        return <BookOpen className="w-4 h-4" />;
    }
  };

  return (
    <div className={`card-base animate-fade-in ${className}`}>
      {/* Card Header */}
      <div className="card-header">
        <div className="flex items-start justify-between">
          <div className="flex items-start gap-3 flex-1 min-w-0">
            <button
              onClick={handleToggleExpanded}
              className="btn-ghost p-1 flex-shrink-0 mt-1"
              aria-label={isExpanded ? "Collapse question" : "Expand question"}
            >
              {isExpanded ? (
                <ChevronDown className="w-4 h-4" />
              ) : (
                <ChevronRight className="w-4 h-4" />
              )}
            </button>
            
            <div className="flex-1 min-w-0">
              <div className="flex items-start justify-between mb-2">
                <h3 className="display-h3 truncate pr-4">
                  {question.title}
                </h3>
                {question.difficulty && getDifficultyChip(question.difficulty)}
              </div>
              
              {/* Metadata row */}
              <div className="flex items-center gap-3 flex-wrap">
                <div className="flex items-center gap-1 caption-text text-muted">
                  {getTypeIcon(question.type)}
                  <span>{question.type || 'question'}</span>
                </div>
                
                {question.points && (
                  <span className="chip-default">
                    {question.points} pts
                  </span>
                )}
                
                {question.timeEstimate && (
                  <div className="flex items-center gap-1 caption-text text-muted">
                    <Clock className="w-3 h-3" />
                    <span>{question.timeEstimate}min</span>
                  </div>
                )}

                {question.isCompleted && (
                  <div className="flex items-center gap-1 text-success">
                    <CheckCircle className="w-3 h-3" />
                    <span className="caption-text">Completed</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Action buttons */}
          {onMarkComplete && (
            <button
              onClick={handleMarkComplete}
              className={`btn-ghost btn-sm ml-2 ${
                question.isCompleted ? 'text-success' : 'text-muted'
              }`}
              title={question.isCompleted ? "Mark incomplete" : "Mark complete"}
            >
              <CheckCircle className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Topics */}
        {question.topics && question.topics.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-3">
            {question.topics.map((topic, idx) => (
              <span key={idx} className="chip-info">
                {topic}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Card Body - Collapsible */}
      {isExpanded && (
        <div className="card-body space-y-4 animate-fade-in">
          {/* Question Content */}
          <div className="body-default leading-relaxed">
            {question.content}
          </div>

          {/* Answer Section */}
          {showAnswer && question.answer && (
            <div className="section-divider">
              <div className="flex items-center gap-2 mb-3">
                <div className="status-dot-success"></div>
                <h4 className="display-h3 text-success">Answer</h4>
              </div>
              <div className="body-default leading-relaxed text-muted">
                {question.answer}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};