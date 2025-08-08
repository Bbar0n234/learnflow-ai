/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        elev: 'var(--color-elev)',
        ink: 'var(--color-ink)',
        muted: 'var(--color-muted)',
        border: 'var(--color-border)',
        primary: {
          DEFAULT: 'var(--color-primary)',
          ink: 'var(--color-primary-ink)'
        },
        info: 'var(--color-info)',
        success: 'var(--color-success)',
        warn: 'var(--color-warn)',
        danger: 'var(--color-danger)'
      },
      borderRadius: {
        'xs': 'var(--radius-xs)',
        'sm': 'var(--radius-sm)',
        'md': 'var(--radius-md)',
        DEFAULT: '0.25rem',
        'none': '0',
        'full': '9999px',
        'lg': '0.5rem',
        'xl': '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem'
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        md: 'var(--shadow-md)',
        lg: 'var(--shadow-lg)'
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Ubuntu', 'Cantarell', 'Noto Sans', 'Arial', 'Apple Color Emoji', 'Segoe UI Emoji', 'sans-serif'],
        display: ['Manrope', 'Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Consolas', 'Liberation Mono', 'Menlo', 'monospace']
      },
      spacing: {
        '1': 'var(--spacing-1)',
        '2': 'var(--spacing-2)',
        '3': 'var(--spacing-3)',
        '4': 'var(--spacing-4)',
        '5': 'var(--spacing-5)',
        '6': 'var(--spacing-6)',
        '8': 'var(--spacing-8)',
        '10': 'var(--spacing-10)',
        '12': 'var(--spacing-12)',
        '16': 'var(--spacing-16)',
      },
      maxWidth: {
        'content-narrow': 'var(--content-width-narrow)',
        'content': 'var(--content-width-default)',
        'content-wide': 'var(--content-width-wide)',
      },
      width: {
        'sidebar': 'var(--sidebar-width)',
      },
      screens: {
        'xs': '475px',
        'sm': '640px',
        'md': '768px',
        'lg': '1024px',
        'xl': '1280px',
        '2xl': '1536px',
      },
      transitionDuration: {
        '120': '120ms',
      },
      animation: {
        'fade-in': 'fadeIn var(--duration-normal) var(--easing)',
        'scale-in': 'scaleIn var(--duration-fast) var(--easing)',
        'hover-lift': 'hoverLift var(--duration-fast) var(--easing)',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        },
        scaleIn: {
          '0%': { opacity: '0', transform: 'scale(0.98)' },
          '100%': { opacity: '1', transform: 'scale(1)' }
        },
        hoverLift: {
          '0%': { transform: 'translateY(0px)' },
          '100%': { transform: 'translateY(-1px)' }
        }
      }
    },
  },
  plugins: [],
}