/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      /* ========== 色彩体系 (Design Token v1) ========== */
      colors: {
        /* --- 主色 Brand --- */
        primary: {
          DEFAULT: '#2563EB',
          hover: '#1D4ED8',
          active: '#1E40AF',
          light: '#EFF6FF',
          border: '#BFDBFE',
        },
        /* --- 辅助色 Accent --- */
        accent: {
          DEFAULT: '#0EA5E9',
          light: '#F0F9FF',
        },
        /* --- 状态色 Status --- */
        success: {
          DEFAULT: '#16A34A',
          light: '#F0FDF4',
        },
        warning: {
          DEFAULT: '#F59E0B',
          light: '#FFFBEB',
        },
        danger: {
          DEFAULT: '#DC2626',
          light: '#FEF2F2',
        },
        /* --- 中性色 Neutral --- */
        bg: {
          base: '#F8FAFC',
          surface: '#FFFFFF',
          elevated: '#F1F5F9',
        },
        border: {
          subtle: '#F1F5F9',
          DEFAULT: '#E2E8F0',
          strong: '#CBD5E1',
        },
        txt: {
          primary: '#0F172A',
          secondary: '#475569',
          tertiary: '#94A3B8',
          disabled: '#CBD5E1',
          inverse: '#FFFFFF',
        },
      },
      /* ========== 字体 ========== */
      fontFamily: {
        sans: ['-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Helvetica Neue', 'Arial', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'SF Mono', 'Consolas', 'monospace'],
      },
      fontSize: {
        xs: ['12px', { lineHeight: '1.4' }],
        sm: ['13px', { lineHeight: '1.4' }],
        base: ['14px', { lineHeight: '1.6' }],
        lg: ['16px', { lineHeight: '1.6' }],
        xl: ['20px', { lineHeight: '1.4' }],
        '2xl': ['24px', { lineHeight: '1.4' }],
      },
      /* ========== 间距 (4px grid) ========== */
      spacing: {
        1: '4px',
        2: '8px',
        3: '12px',
        4: '16px',
        5: '20px',
        6: '24px',
        8: '32px',
        10: '40px',
      },
      /* ========== 圆角 ========== */
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
        xl: '12px',
      },
      /* ========== 阴影 ========== */
      boxShadow: {
        sm: '0 1px 2px rgba(15,23,42,0.04)',
        card: '0 2px 8px rgba(15,23,42,0.06)',
        lg: '0 4px 16px rgba(15,23,42,0.08)',
        xl: '0 8px 32px rgba(15,23,42,0.12)',
      },
      /* ========== 动画 ========== */
      animation: {
        'fade-in': 'fadeIn 0.3s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
      },
      keyframes: {
        fadeIn: { from: { opacity: '0' }, to: { opacity: '1' } },
        slideUp: { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'translateY(0)' } },
      },
    },
  },
  plugins: [],
}
