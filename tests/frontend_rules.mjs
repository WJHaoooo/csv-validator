// Optional frontend unit tests: Node built-ins only, no npm dependencies.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

const source = await readFile(new URL("../src/csv_validator/static/rules.js", import.meta.url), "utf8");
const rules = await import("data:text/javascript;base64," + Buffer.from(source).toString("base64"));

assert.deepEqual(rules.defaultRule(), {type:"str", required:false});
const order = ["10", "2", "missing"];
const settings = new Map(order.map(name => [name, rules.defaultRule()]));
assert.deepEqual(rules.activeNames(order, ["10", "2"], new Set(["2"])), ["2", "missing"]);
const serialized = rules.serializeSchema(order, settings);
assert.ok(serialized.indexOf('"10"') < serialized.indexOf('"2"'));
assert.ok(serialized.indexOf('"2"') < serialized.indexOf('"missing"'));
assert.deepEqual(JSON.parse(serialized).columns["missing"], {type:"str", required:false});
assert.throws(() => rules.serializeSchema([], settings));

const special = ['name "quoted"\nline', "__proto__", "範例"];
const specialSchema = JSON.parse(rules.serializeSchema(special, new Map(special.map(name => [name, rules.defaultRule()]))));
assert.ok(special.every(name => Object.hasOwn(specialSchema.columns, name)));
assert.equal(Object.prototype.polluted, undefined);

const note = 'brace } bracket ] quote " slash \\ and newline\nUnicode 範例';
const records = Array.from({length:8}, (_, index) =>
  `  {"id":${index ? index : "9007199254740993"},"note":${JSON.stringify(note)}}`);
const json = "[\n" + records.join(",\n") + "\n]\n";
const preview = rules.firstJsonRecords(json);
assert.ok(preview.includes("9007199254740993"));
assert.ok(!preview.includes('"id":5'));
assert.equal(JSON.parse(preview).length, 5);
assert.equal(JSON.parse(preview)[0].note, note);
assert.equal(rules.firstJsonRecords("[]\n"), "[]");
const nested = '[{"a":[{"b":"}"}]},{"c":true}]';
assert.deepEqual(JSON.parse(rules.firstJsonRecords(nested)), JSON.parse(nested));
assert.throws(() => rules.firstJsonRecords('{"not":"an array"}'));

console.log("Frontend rule and lossless JSON preview tests passed.");
