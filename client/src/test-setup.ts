import "@testing-library/jest-dom/vitest";
// jsdom does not implement IndexedDB; polyfill it for any test that
// exercises the required IndexedDB-backed client storage hooks.
import "fake-indexeddb/auto";
