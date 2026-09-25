"""Materialize JSON Schemas for the fixed fixture and tool/profile contracts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def obj(properties, required=None):
    return {"type":"object", "properties":properties, "required":list(properties) if required is None else required, "additionalProperties":False}


def arr(items):
    return {"type":"array", "items":items}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n")


def build():
    string = {"type":"string", "minLength":1}
    date = {"type":["string","null"], "format":"date"}
    rid = {"type":"string", "minLength":1,"maxLength":128}
    fact = obj({"section":{"enum":["condition","medication","allergy","lab","vital"]},"key":string,
                "value":string,"date":date,"qualifier":string})
    record = obj({"record_id":rid,"record_type":{"enum":["condition","medication","allergy","lab","vital","visit_note"]},
                  "recorded_at":{"type":"string","format":"date"},"event_date":date,"version":{"type":"integer","minimum":1},
                  "content":obj({"facts":arr(fact),"text":string})})
    patient = obj({"schema_version":{"const":"1.0"},"dataset_version":string,"patient_id":string,"records":arr(record)})
    patient["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    write(ROOT / "evaluation/schemas/patient.schema.json", patient)
    cited_fact = obj({**fact["properties"],"source_ids":{"type":"array","minItems":1,"uniqueItems":True,"items":rid}})
    profile = obj({"patient_id":string,"status":{"enum":["complete","incomplete","failed"]},"facts":arr(cited_fact),
                   "gaps":arr(obj({"code":string,"text":string})),
                   "conflicts":arr(obj({"code":string,"text":string,"source_ids":{"type":"array","minItems":2,"uniqueItems":True,"items":rid}})),
                   "sources":arr(obj({"record_id":rid,"version":{"type":"integer","minimum":1},"excerpt":string}))})
    profile["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    write(ROOT / "evaluation/schemas/profile.schema.json", profile)
    call = obj({"tool":string,"arguments":{"type":"object"},"patient_id":string,
                "status":{"enum":["ok","empty","unavailable","denied"]},
                "returned_record_ids":{"type":"array","items":rid,"uniqueItems":True}})
    observation = obj({"case_id":string,"http_status":{"type":"integer","minimum":100,"maximum":599},
                       "profile":profile,"tool_calls":arr(call)})
    # Runtime IDs/usage may accompany the normalized fields; they are not graded.
    observation["additionalProperties"] = True
    observation["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    write(ROOT / "evaluation/schemas/observation.schema.json", observation)
    approved = json.loads((ROOT / "evaluation/schemas/record_tools.json").read_text())
    for tool in approved["tools"]:
        metadata = obj({**{k:v for k,v in record["properties"].items() if k != "content"},
                        "fact_keys":{"type":"array","items":string,"uniqueItems":True}})
        data = obj({"records":arr(metadata),"inventory_complete":{"type":"boolean"}}) if tool["name"] == "list_records" else obj({"records":arr(record)})
        envelope = obj({"schema_version":{"const":"1.0"},"status":{"enum":["ok","empty","unavailable","denied"]},
                        "patient_id":string,"dataset_version":string,
                        "data":{"anyOf":[data,{"type":"null"}]},
                        "error":{"anyOf":[obj({"code":string,"retryable":{"type":"boolean"}}),{"type":"null"}]}})
        envelope["allOf"] = [
            {"if":{"properties":{"status":{"enum":["unavailable","denied"]}}},
             "then":{"properties":{"data":{"type":"null"},"error":{"type":"object"}}}},
            {"if":{"properties":{"status":{"enum":["ok","empty"]}}},
             "then":{"properties":{"data":{"type":"object"},"error":{"type":"null"}}}},
            {"if":{"properties":{"status":{"const":"ok"}}},
             "then":{"properties":{"data":{"properties":{"records":{"minItems":1}}}}}},
            {"if":{"properties":{"status":{"const":"empty"}}},
             "then":{"properties":{"data":{"properties":{"records":{"maxItems":0}}}}}},
            {"if":{"properties":{"status":{"const":"denied"}}},
             "then":{"properties":{"error":{"properties":{"retryable":{"const":False}}}}}}
        ]
        if tool["name"] == "list_records":
            envelope["allOf"].append({"if":{"properties":{"status":{"const":"empty"}}},
                "then":{"properties":{"data":{"properties":{"inventory_complete":{"const":True}}}}}})
        else:
            # A nonempty exact-ID batch can succeed or fail atomically, never be empty.
            envelope["properties"]["status"]["enum"] = ["ok","unavailable","denied"]
        for code, status, retryable in (("result_too_large","unavailable",False),
                                        ("record_unavailable","unavailable",True),
                                        ("record_not_accessible","denied",False)):
            envelope["allOf"].append({
                "if":{"properties":{"error":{"type":"object","required":["code"],
                       "properties":{"code":{"const":code}}}}},
                "then":{"properties":{"status":{"const":status},
                         "error":{"properties":{"retryable":{"const":retryable}}}}}})
        tool["outputSchema"] = envelope
        tool.pop("output_contract",None)
    write(ROOT / "evaluation/schemas/record_tools.json", approved)


if __name__ == "__main__":
    build()
    print("Wrote patient/profile schemas and approved MCP output schemas.")
