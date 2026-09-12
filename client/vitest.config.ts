import { defineConfig, mergeConfig } from "vitest/config";
import viteConfig from "./vite.config";
import * as path from "path";

export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test-setup.ts"],
      include: [
        "src/**/*.{test,spec}.{ts,tsx}",
        "../projects/uwuchat/client/**/*.{test,spec}.{ts,tsx}",
        "../extensions/auth/client/**/*.{test,spec}.{ts,tsx}",
      ],
      css: {
        modules: {
          classNameStrategy: "non-scoped",
        },
      },
      // Vitest needs to process extensions and project dirs for the
      // overlay plugin and extension loader to work in tests.
      server: {
        deps: {
          inline: [
            /extensions\/auth\/client/,
            /projects\/uwuchat\/client/,
          ],
        },
      },
      coverage: {
        provider: "v8",
        reporter: ["text", "text-summary", "html", "lcov"],
        reportsDirectory: "./coverage",
        include: [
          "src/**/*.{ts,tsx}",
          "../projects/uwuchat/client/**/*.{ts,tsx}",
        ],
        exclude: [
          "src/**/*.{test,spec}.{ts,tsx}",
          "../projects/uwuchat/client/**/*.{test,spec}.{ts,tsx}",
        ],
      },
    },
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
        // Resolve react and friends from the client's node_modules
        // when project components (../projects/uwuchat/client/)
        // import them but have no node_modules of their own.
        react: path.resolve(__dirname, "node_modules/react"),
        "react-dom": path.resolve(__dirname, "node_modules/react-dom"),
        "react-i18next": path.resolve(
          __dirname, "node_modules/react-i18next",
        ),
        "react-router-dom": path.resolve(
          __dirname, "node_modules/react-router-dom",
        ),
        // Same story for the testing-library packages: project test
        // files live outside client/ and have no node_modules of their
        // own, so bare imports would otherwise fail to resolve in CI's
        // fresh `npm ci` install (node resolution never reaches
        // client/node_modules from ../projects/uwuchat/client).
        "@testing-library/react": path.resolve(
          __dirname, "node_modules/@testing-library/react",
        ),
        "@testing-library/user-event": path.resolve(
          __dirname, "node_modules/@testing-library/user-event",
        ),
        "@testing-library/jest-dom": path.resolve(
          __dirname, "node_modules/@testing-library/jest-dom",
        ),
      },
    },
  }),
);
