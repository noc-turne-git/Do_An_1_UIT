import type { ButtonHTMLAttributes, PropsWithChildren } from 'react'

type Props = PropsWithChildren<ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet' }>
export function Button({ variant = 'secondary', className = '', children, ...props }: Props) {
  const variants = {
    primary: 'bg-neutral-900 text-white hover:bg-neutral-700',
    secondary: 'border border-neutral-200 bg-white text-neutral-900 hover:bg-neutral-50',
    quiet: 'text-neutral-700 hover:bg-neutral-100',
  }
  return <button className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition disabled:opacity-50 ${variants[variant]} ${className}`} {...props}>{children}</button>
}
