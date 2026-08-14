import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { Type } from "typebox";

type JsonObject = Record<string, unknown>;

const gateway = process.env.TOOLATHLON_MCP_GATEWAY_URL;
if (!gateway) throw new Error("TOOLATHLON_MCP_GATEWAY_URL is required");

function visibleName(name: string): string {
  return `mcp__toolathlon__${name.replace(/[^A-Za-z0-9_-]/g, "_")}`;
}

class ClassicSseClient {
  private endpoint?: URL;
  private nextId = 0;
  private pending = new Map<number, { resolve: (value: JsonObject) => void; reject: (error: Error) => void }>();
  private abort = new AbortController();
  private readyResolve!: () => void;
  private ready = new Promise<void>((resolve) => { this.readyResolve = resolve; });

  async connect(): Promise<void> {
    const response = await fetch(gateway!, { signal: this.abort.signal, headers: { Accept: "text/event-stream" } });
    if (!response.ok || !response.body) throw new Error(`MCP SSE connection failed: HTTP ${response.status}`);
    void this.readEvents(response.body).catch((error) => {
      for (const waiter of this.pending.values()) waiter.reject(error instanceof Error ? error : new Error(String(error)));
      this.pending.clear();
    });
    await this.ready;
    await this.request("initialize", {
      protocolVersion: "2024-11-05",
      capabilities: {},
      clientInfo: { name: "toolathlon-pi-adapter", version: "1" },
    });
    await this.notify("notifications/initialized", {});
  }

  close(): void { this.abort.abort(); }

  async request(method: string, params: JsonObject): Promise<JsonObject> {
    await this.ready;
    const id = ++this.nextId;
    const response = new Promise<JsonObject>((resolve, reject) => this.pending.set(id, { resolve, reject }));
    await this.post({ jsonrpc: "2.0", id, method, params });
    return response;
  }

  async notify(method: string, params: JsonObject): Promise<void> {
    await this.post({ jsonrpc: "2.0", method, params });
  }

  private async post(payload: JsonObject): Promise<void> {
    if (!this.endpoint) throw new Error("MCP endpoint is not ready");
    const response = await fetch(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
      signal: this.abort.signal,
    });
    if (!response.ok && response.status !== 202) throw new Error(`MCP POST failed: HTTP ${response.status}`);
  }

  private async readEvents(stream: ReadableStream<Uint8Array>): Promise<void> {
    const reader = stream.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n");
      let boundary: number;
      while ((boundary = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, boundary).replace(/\r/g, "");
        buffer = buffer.slice(boundary + 2);
        let event = "message";
        const data: string[] = [];
        for (const line of block.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
        }
        if (!data.length) continue;
        if (event === "endpoint") {
          const endpoint = new URL(data.join("\n"), gateway!);
          const gatewayUrl = new URL(gateway!);
          if (endpoint.origin !== gatewayUrl.origin || !["127.0.0.1", "localhost", "[::1]"].includes(endpoint.hostname)) {
            throw new Error(`MCP endpoint escaped the task Gateway origin: ${endpoint.origin}`);
          }
          this.endpoint = endpoint;
          this.readyResolve();
        } else if (event === "message") {
          const message = JSON.parse(data.join("\n")) as JsonObject;
          const id = message.id;
          if (typeof id !== "number") continue;
          const waiter = this.pending.get(id);
          if (!waiter) continue;
          this.pending.delete(id);
          if (message.error) waiter.reject(new Error(JSON.stringify(message.error)));
          else waiter.resolve((message.result as JsonObject) ?? {});
        }
      }
    }
  }
}

export default async function (pi: ExtensionAPI) {
  const client = new ClassicSseClient();
  await client.connect();
  const tools: unknown[] = [];
  let cursor: string | undefined;
  do {
    const listed = await client.request("tools/list", cursor ? { cursor } : {});
    if (!Array.isArray(listed.tools)) throw new Error("MCP tools/list returned no tools array");
    tools.push(...listed.tools);
    cursor = typeof listed.nextCursor === "string" && listed.nextCursor ? listed.nextCursor : undefined;
  } while (cursor);
  const names = new Set<string>();
  for (const item of tools) {
    if (!item || typeof item !== "object") throw new Error("invalid MCP tool record");
    const tool = item as JsonObject;
    if (typeof tool.name !== "string") throw new Error("MCP tool has no name");
    const name = visibleName(tool.name);
    if (names.has(name)) throw new Error(`Pi-visible MCP tool collision: ${name}`);
    names.add(name);
    pi.registerTool({
      name,
      label: tool.name,
      description: typeof tool.description === "string" ? tool.description : "",
      parameters: Type.Unsafe(tool.inputSchema ?? { type: "object", properties: {} }),
      execute: async (_toolCallId, params) => {
        const result = await client.request("tools/call", { name: tool.name, arguments: params as JsonObject });
        if (result.isError === true) throw new Error(JSON.stringify(result.content ?? result));
        const rawContent = Array.isArray(result.content) ? result.content : [result];
        const content = rawContent.map((item) => {
          if (item && typeof item === "object" && ((item as JsonObject).type === "text" || (item as JsonObject).type === "image")) return item;
          return { type: "text", text: JSON.stringify(item) };
        });
        return { content: content as never, details: { gatewayToolName: tool.name } };
      },
    });
  }
  pi.on("session_shutdown", () => client.close());
}
