import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      globals: globals.browser,
    },
    rules: {
      'no-restricted-syntax': [
        'error',
        {
          selector:
            'JSXAttribute[name.name="style"] JSXExpressionContainer > ObjectExpression',
          message:
            'No inline style objects — use a colocated CSS Module. ' +
            'If this value is genuinely dynamic (portal position, state-driven ' +
            'color, computed dimension, Konva API requirement, CSS custom ' +
            'property), add a disable comment explaining why. ' +
            'See plans/inline-styles-refactor.md.',
        },
      ],
    },
  },
])
