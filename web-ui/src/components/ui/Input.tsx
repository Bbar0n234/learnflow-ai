import { forwardRef, type InputHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { cn } from '../../utils/cn'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean
}

interface TextAreaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  error?: boolean
}

const inputStyles = cn(
  'flex w-full rounded-xs border border-border bg-elev px-3 py-2',
  'text-base text-ink placeholder:text-muted',
  'ring-offset-bg transition-all duration-150',
  'file:border-0 file:bg-transparent file:text-sm file:font-medium',
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary focus-visible:ring-offset-2',
  'hover:border-border/80',
  'disabled:cursor-not-allowed disabled:opacity-50'
)

const Input = forwardRef<HTMLInputElement, InputProps>(({
  className,
  type,
  error,
  ...props
}, ref) => {
  return (
    <input
      type={type}
      className={cn(
        inputStyles,
        error && 'border-danger focus-visible:ring-danger',
        className
      )}
      ref={ref}
      {...props}
    />
  )
})

const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(({
  className,
  error,
  ...props
}, ref) => {
  return (
    <textarea
      className={cn(
        inputStyles,
        'min-h-[80px] resize-vertical',
        error && 'border-danger focus-visible:ring-danger',
        className
      )}
      ref={ref}
      {...props}
    />
  )
})

Input.displayName = 'Input'
TextArea.displayName = 'TextArea'

export { Input, TextArea }