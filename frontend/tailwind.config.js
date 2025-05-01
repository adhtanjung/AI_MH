/** @type {import('tailwindcss').Config} */
export default {
    content: [
      "./index.html",
      "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
      extend: {
        colors: {
          // Apple-inspired color palette
          blue: {
            50: '#f0f9ff',
            100: '#e0f2fe',
            200: '#b9e6fe',
            300: '#7dd3fc',
            400: '#38bdf8',
            500: '#0284c7', // Primary blue
            600: '#0369a1',
            700: '#075985',
            800: '#0c4a6e',
            900: '#0c3256',
          },
          neutral: {
            50: '#fafafa',  // Background
            100: '#f4f4f5', // Subtle background
            200: '#e4e4e7', // Borders
            300: '#d4d4d8',
            400: '#a1a1aa', // Muted text
            500: '#71717a', // Secondary text
            600: '#52525b',
            700: '#3f3f46',
            800: '#27272a', // Primary text
            900: '#18181b',
          }
        },
        boxShadow: {
          'sm': '0 1px 2px 0 rgba(0, 0, 0, 0.05)',
          'DEFAULT': '0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06)',
          'md': '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
          'lg': '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)',
          'xl': '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
          '2xl': '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          'apple': '0 8px 30px rgba(0, 0, 0, 0.12)',
        },
        borderRadius: {
          'xl': '0.75rem',
          '2xl': '1rem',
          '3xl': '1.5rem',
        },
        fontFamily: {
          sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
        },
        animation: {
          'fade-in': 'fade-in 0.4s ease-out forwards',
        },
        keyframes: {
          'fade-in': {
            '0%': { opacity: '0', transform: 'translateY(10px)' },
            '100%': { opacity: '1', transform: 'translateY(0)' },
          },
        },
      },
    },
    plugins: [],
  }