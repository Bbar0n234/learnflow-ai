import { forwardRef, type HTMLAttributes, type ReactNode } from 'react'
import { cn } from '../../utils/cn'

export type CardVariant = 'default' | 'elevated' | 'bordered'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: CardVariant
}

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {}

interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {
  children: ReactNode
}

interface CardDescriptionProps extends HTMLAttributes<HTMLParagraphElement> {
  children: ReactNode
}

interface CardContentProps extends HTMLAttributes<HTMLDivElement> {}

interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {}

const cardVariants = {
  default: 'bg-elev border border-border',
  elevated: 'bg-elev border border-border shadow-md',
  bordered: 'bg-bg border-2 border-border'
}

const Card = forwardRef<HTMLDivElement, CardProps>(({
  className,
  variant = 'default',
  ...props
}, ref) => (
  <div
    ref={ref}
    className={cn(
      'rounded-sm p-4 transition-colors',
      cardVariants[variant],
      className
    )}
    {...props}
  />
))

const CardHeader = forwardRef<HTMLDivElement, CardHeaderProps>(({
  className,
  ...props
}, ref) => (
  <div
    ref={ref}
    className={cn('flex flex-col space-y-1.5 p-0 pb-4', className)}
    {...props}
  />
))

const CardTitle = forwardRef<HTMLHeadingElement, CardTitleProps>(({
  className,
  children,
  ...props
}, ref) => (
  <h3
    ref={ref}
    className={cn('text-xl font-semibold text-ink font-display leading-none tracking-tight', className)}
    {...props}
  >
    {children}
  </h3>
))

const CardDescription = forwardRef<HTMLParagraphElement, CardDescriptionProps>(({
  className,
  children,
  ...props
}, ref) => (
  <p
    ref={ref}
    className={cn('text-base text-muted leading-relaxed', className)}
    {...props}
  >
    {children}
  </p>
))

const CardContent = forwardRef<HTMLDivElement, CardContentProps>(({
  className,
  ...props
}, ref) => (
  <div
    ref={ref}
    className={cn('p-0', className)}
    {...props}
  />
))

const CardFooter = forwardRef<HTMLDivElement, CardFooterProps>(({
  className,
  ...props
}, ref) => (
  <div
    ref={ref}
    className={cn('flex items-center p-0 pt-4', className)}
    {...props}
  />
))

Card.displayName = 'Card'
CardHeader.displayName = 'CardHeader'
CardTitle.displayName = 'CardTitle'
CardDescription.displayName = 'CardDescription'
CardContent.displayName = 'CardContent'
CardFooter.displayName = 'CardFooter'

export {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter
}