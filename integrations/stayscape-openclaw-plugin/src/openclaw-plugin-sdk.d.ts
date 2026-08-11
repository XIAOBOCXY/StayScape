declare module "openclaw/plugin-sdk/tool-plugin" {
  type ToolContext = { signal?: AbortSignal };
  type ToolDefinition = {
    name: string;
    label?: string;
    description: string;
    parameters: unknown;
    outputSchema?: unknown;
    optional?: boolean;
    execute: (params: any, config: any, context: ToolContext) => Promise<unknown> | unknown;
  };
  type ToolFactory = (definition: ToolDefinition) => unknown;
  export function defineToolPlugin(options: {
    id: string;
    name: string;
    description: string;
    configSchema?: unknown;
    tools: (tool: ToolFactory) => unknown[];
  }): unknown;
}
