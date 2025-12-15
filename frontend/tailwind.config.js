/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                app: 'var(--bg-app)',
                panel: 'var(--bg-panel)',
                hover: 'var(--bg-hover)',
                active: 'var(--bg-active)',
                primary: 'var(--text-primary)',
                secondary: 'var(--text-secondary)',
                muted: 'var(--text-muted)',
                trade: {
                    up: 'var(--trade-up)',
                    down: 'var(--trade-down)',
                    accent: 'var(--trade-accent)',
                },
                border: {
                    subtle: 'var(--border-subtle)',
                }
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
            }
        },
    },
    plugins: [],
}
