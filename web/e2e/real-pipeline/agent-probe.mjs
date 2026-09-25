/**
 * Preflight checks so real-pipeline Playwright never confuses the contract mock
 * with the FastAPI agent service.
 */

const MOCK_HINT =
  "Stop `node e2e/mock-api/server.mjs` or choose another port via REAL_AGENT_PORT.";

/**
 * @param {string} baseUrl Agent base URL without trailing slash.
 * @returns {Promise<{ status: string, dependencies: Record<string, string> }>}
 */
export async function assertRealAgent(baseUrl) {
  let liveRes;
  try {
    liveRes = await fetch(`${baseUrl}/health/live`, {
      signal: AbortSignal.timeout(5_000),
    });
  } catch (err) {
    throw new Error(
      `Agent not reachable at ${baseUrl}: ${err instanceof Error ? err.message : String(err)}`,
    );
  }

  if (!liveRes.ok) {
    throw new Error(`Agent ${baseUrl}/health/live returned HTTP ${liveRes.status}.`);
  }

  const liveBody = await liveRes.json();
  if (liveBody?.status !== "ok" || !("dependencies" in liveBody)) {
    throw new Error(
      `Port ${new URL(baseUrl).port} is not the FastAPI agent (contract mock lacks ` +
        `"dependencies" on /health/live). ${MOCK_HINT}`,
    );
  }

  const readyRes = await fetch(`${baseUrl}/health/ready`, {
    signal: AbortSignal.timeout(5_000),
  });
  if (!readyRes.ok) {
    throw new Error(`Agent ${baseUrl}/health/ready returned HTTP ${readyRes.status}.`);
  }
  const readyBody = await readyRes.json();
  if (readyBody?.dependencies?.database !== "ok") {
    throw new Error(
      `Agent database is not ready (${JSON.stringify(readyBody?.dependencies ?? {})}).`,
    );
  }

  return readyBody;
}

/**
 * @param {string} mcpOrigin e.g. http://127.0.0.1:8001
 */
export async function assertMcpPort(mcpOrigin) {
  try {
    const res = await fetch(`${mcpOrigin}/mcp`, {
      method: "GET",
      signal: AbortSignal.timeout(5_000),
    });
    // Any HTTP response from the MCP route means something is listening on 8001.
    if (res.status >= 500) {
      throw new Error(`Records MCP ${mcpOrigin}/mcp returned HTTP ${res.status}.`);
    }
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new Error(`Timed out probing records MCP at ${mcpOrigin}.`);
    }
    throw new Error(
      `Records MCP not reachable at ${mcpOrigin}: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
}
