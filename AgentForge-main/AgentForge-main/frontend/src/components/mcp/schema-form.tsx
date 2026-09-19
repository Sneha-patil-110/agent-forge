"use client";

type JsonSchemaProperty = {
  type?: string;
  description?: string;
  enum?: unknown[];
};

type JsonSchema = {
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
};

export function SchemaForm({
  schema,
  values,
  onChange,
}: {
  schema: Record<string, unknown>;
  values: Record<string, unknown>;
  onChange: (values: Record<string, unknown>) => void;
}) {
  const typed = schema as JsonSchema;
  const properties = typed.properties ?? {};
  const required = new Set(typed.required ?? []);
  const names = Object.keys(properties);

  if (names.length === 0) {
    return <p className="text-xs text-muted-foreground">This tool takes no parameters.</p>;
  }

  const setField = (name: string, value: unknown) => {
    onChange({ ...values, [name]: value });
  };

  return (
    <div className="space-y-2.5">
      {names.map((name) => {
        const prop = properties[name] ?? {};
        const label = (
          <label htmlFor={`mcp-arg-${name}`} className="font-mono text-xs text-primary">
            {name}
            {required.has(name) && <span className="text-status-failed">*</span>}
            {prop.description && <span className="ml-1.5 font-sans text-muted-foreground">— {prop.description}</span>}
          </label>
        );

        if (prop.enum && prop.enum.length > 0) {
          return (
            <div key={name} className="space-y-1">
              {label}
              <select
                id={`mcp-arg-${name}`}
                value={typeof values[name] === "string" ? (values[name] as string) : ""}
                onChange={(event) => setField(name, event.target.value)}
                className="h-8 w-full rounded-md border border-border/60 bg-surface-2/40 px-2 text-xs text-foreground"
              >
                <option value="" disabled>
                  Select…
                </option>
                {prop.enum.map((option) => (
                  <option key={String(option)} value={String(option)}>
                    {String(option)}
                  </option>
                ))}
              </select>
            </div>
          );
        }

        if (prop.type === "boolean") {
          return (
            <div key={name} className="flex items-center gap-2">
              <input
                id={`mcp-arg-${name}`}
                type="checkbox"
                checked={Boolean(values[name])}
                onChange={(event) => setField(name, event.target.checked)}
                className="size-3.5"
              />
              {label}
            </div>
          );
        }

        if (prop.type === "number" || prop.type === "integer") {
          return (
            <div key={name} className="space-y-1">
              {label}
              <input
                id={`mcp-arg-${name}`}
                type="number"
                value={typeof values[name] === "number" ? values[name] as number : ""}
                onChange={(event) =>
                  setField(name, event.target.value === "" ? undefined : Number(event.target.value))
                }
                className="h-8 w-full rounded-md border border-border/60 bg-surface-2/40 px-2 text-xs text-foreground"
              />
            </div>
          );
        }

        if (prop.type === "string" || prop.type === undefined) {
          return (
            <div key={name} className="space-y-1">
              {label}
              <input
                id={`mcp-arg-${name}`}
                type="text"
                value={typeof values[name] === "string" ? (values[name] as string) : ""}
                onChange={(event) => setField(name, event.target.value)}
                className="h-8 w-full rounded-md border border-border/60 bg-surface-2/40 px-2 text-xs text-foreground"
              />
            </div>
          );
        }

        return (
          <div key={name} className="space-y-1">
            {label}
            <textarea
              id={`mcp-arg-${name}`}
              value={values[name] !== undefined ? JSON.stringify(values[name]) : ""}
              onChange={(event) => {
                try {
                  setField(name, JSON.parse(event.target.value));
                } catch {
                }
              }}
              placeholder="JSON value"
              rows={2}
              className="w-full rounded-md border border-border/60 bg-surface-2/40 px-2 py-1.5 font-mono text-xs text-foreground"
            />
          </div>
        );
      })}
    </div>
  );
}
