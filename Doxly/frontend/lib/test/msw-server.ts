import { setupServer } from "msw/node";

/**
 * Shared MSW server for component/integration tests (testing.md §2.3) —
 * intercepts at the network boundary so tests exercise the same
 * request-construction code in lib/api/* that production does, rather than
 * mocking fetch() directly. Each test file supplies its own handlers via
 * `mswServer.use(...)`.
 */
export const mswServer = setupServer();
