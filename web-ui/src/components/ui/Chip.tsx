import { forwardRef, type HTMLAttributes, type ReactNode } from 'react'
import { cn } from '../../utils/cn'
import { X } from 'lucide-react'

export type ChipVariant = 'default' | 'info' | 'success' | 'warn' | 'danger'
export type ChipSize = 'sm' | 'md'

interface ChipProps extends HTMLAttributes<HTMLDivElement> {
  variant?: ChipVariant
  size?: ChipSize
  removable?: boolean
  onRemove?: () => void
  children: ReactNode
}

const chipVariants = {
  default: 'bg-elev text-ink border border-border',
  info: 'bg-info/10 text-info border border-info/20',
  success: 'bg-success/10 text-success border border-success/20',
  warn: 'bg-warn/10 text-warn border border-warn/20',
  danger: 'bg-danger/10 text-danger border border-danger/20'
}

const chipSizes = {
  sm: 'h-6 px-2 text-xs',
  md: 'h-7 px-3 text-xs'
}

const Chip = forwardRef<HTMLDivElement, ChipProps>(({
  className,
  variant = 'default',
  size = 'md',
  removable = false,
  onRemove,
  children,
  ...props
}, ref) => {
  return (
    <div
      ref={ref}
      className={cn(
        'inline-flex items-center gap-1.5 rounded font-medium',
        'transition-colors',
        chipVariants[variant],
        chipSizes[size],
        className
      )}
      {...props}
    >
      <span className="truncate">{children}</span>
      {removable && onRemove && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onRemove()
          }}
          className="inline-flex h-4 w-4 items-center justify-center rounded hover:bg-black/10 focus:outline-none focus:bg-black/10 transition-colors"
          aria-label="Remove"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </div>
  )
})

Chip.displayName = 'Chip'

export { Chip }