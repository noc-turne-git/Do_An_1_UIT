import type { PropsWithChildren } from 'react'

export function Modal({ open, onClose, children, className = '' }: PropsWithChildren<{ open: boolean; onClose: () => void; className?: string }>) {
  if (!open) return null
  return <div className="fixed inset-0 z-50 grid place-items-center bg-black/35 p-4" onMouseDown={onClose}>
    <div className={`max-h-[90vh] w-full max-w-lg overflow-auto rounded-2xl bg-white p-6 shadow-xl ${className}`} onMouseDown={(event) => event.stopPropagation()}>{children}</div>
  </div>
}
