/** @type {import('tailwindcss').Config} */
export default {
    content: [
        "./index.html",
        "./src/**/*.{js,ts,jsx,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                app: '#0B0F14',
                panel: '#121826',
                hover: '#1C2533',
                active: '#2A3441',
                primary: '#FFFFFF',
                secondary: '#9CA3AF',
                muted: '#6B7280',
                trade: {
                    up: '#2ABD85',
                    down: '#F23645',
                    accent: '#2962FF',
                },
                border: {
                    subtle: '#1E2838',
                }
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', 'sans-serif'],
            }
        },
    },
    plugins: [],
}
