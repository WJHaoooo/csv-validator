// Schema order is explicit: JavaScript objects reorder integer-like keys.
export function defaultRule() {
  return {type: "str", required: false};
}
export function activeNames(order, columns, selected) {
  const present = new Set(columns);
  return order.filter((name) => !present.has(name) || selected.has(name));
}
export function serializeSchema(names, rules) {
  if (!names.length) throw new Error("至少保留一個 Schema 欄位。");
  const entries = names.map((name) => {
    const rule = rules.get(name);
    return `    ${JSON.stringify(name)}: {\n      "type": ${JSON.stringify(rule.type)},\n      "required": ${rule.required}\n    }`;
  });
  return `{\n  "columns": {\n${entries.join(",\n")}\n  }\n}\n`;
}
// Slice complete top-level records from server-produced JSON without parsing
// numeric values into JS Number (which would round large Python integers).
export function firstJsonRecords(text, limit = 5) {
  let inString = false;
  let escaped = false;
  let depth = 0;
  let count = 0;
  let lastEnd = 0;
  if (!text.trimStart().startsWith("[")) throw new Error("伺服器未回傳 JSON 陣列。");
  for (let index = 0; index < text.length; index++) {
    const character = text[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      continue;
    }
    if (character === '"') inString = true;
    else if (character === "[" || character === "{") depth++;
    else if (character === "]" || character === "}") {
      depth--;
      if (character === "}" && depth === 1) {
        lastEnd = index + 1;
        count++;
        if (count === limit) break;
      }
    }
  }
  return lastEnd ? text.slice(0, lastEnd).trimEnd() + "\n]" : "[]";
}
