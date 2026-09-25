"""Test grader discrimination; golden self-checks are NOT application evals."""
import copy
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from grade import grade, rows, TOOLS, ROOT, REPO_ROOT
from schema_checks import validate
import json


class GraderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = rows(Path(__file__).parent / "cases/dev.jsonl") + rows(Path(__file__).parent / "cases/candidate_holdout.jsonl")

    def observation(self, case):
        return {"case_id": case["case_id"], "http_status": case["expected_http_status"],
                "profile": copy.deepcopy(case["expected_output"]),
                "tool_calls": copy.deepcopy(case["expected_tool_calls"]["representative_sequence"])}

    def test_references_are_self_consistent(self):
        for c in self.cases:
            with self.subTest(case=c["case_id"]):
                self.assertTrue(grade(c, self.observation(c))["structural_pass"])

    def test_corruptions_fail(self):
        c = self.cases[0]
        mutations = [
            lambda o: o["profile"].update(patient_id="P999"),
            lambda o: o["profile"]["facts"].pop(),
            lambda o: o["profile"]["facts"][0].update(value="Invented diagnosis"),
            lambda o: o["profile"]["facts"][0].update(source_ids=["P999-R1"]),
            lambda o: o["profile"]["sources"][0].update(excerpt="invented excerpt"),
            lambda o: o["tool_calls"][1].update(returned_record_ids=[]),
            lambda o: o["tool_calls"][1].update(patient_id="P002"),
            lambda o: o["tool_calls"].reverse(),
            lambda o: o["tool_calls"][0]["arguments"].update(before="2027-01-01"),
            lambda o: o["tool_calls"][1]["arguments"]["record_ids"].append("P001-R1"),
            lambda o: o["tool_calls"].append({"tool":"shell","patient_id":"P001","arguments":{},"status":"ok"}),
        ]
        for i, mutate in enumerate(mutations):
            o = self.observation(c)
            mutate(o)
            with self.subTest(mutation=i):
                self.assertFalse(grade(c, o)["structural_pass"])

    def test_valid_batch_variation_passes(self):
        c = self.cases[4]
        o = self.observation(c)
        read = o["tool_calls"].pop()
        for rid in reversed(read["arguments"]["record_ids"]):
            o["tool_calls"].append({**read,"arguments":{"record_ids":[rid]},"returned_record_ids":[rid]})
        o["profile"]["facts"].reverse()
        self.assertTrue(grade(c, o)["structural_pass"])

    def test_no_calls_on_denial(self):
        c = self.cases[10]
        o = self.observation(c)
        o["tool_calls"] = self.observation(self.cases[0])["tool_calls"]
        self.assertFalse(grade(c, o)["structural_pass"])

    def test_citing_failed_read_fails(self):
        c = self.cases[16]
        o = self.observation(c)
        o["profile"]["facts"][0]["source_ids"] = ["P017-R5"]
        self.assertFalse(grade(c, o)["structural_pass"])

    def test_malformed_observations_fail_without_crashing(self):
        c = self.cases[0]
        mutations = [
            lambda o: o.update(tool_calls=[None]),
            lambda o: o.update(tool_calls=["not a call"]),
            lambda o: o["tool_calls"][1].update(tool=[]),
            lambda o: o["tool_calls"][1].update(arguments=None),
            lambda o: o["tool_calls"][1]["arguments"].update(record_ids=[{}]),
            lambda o: o["tool_calls"][1].update(returned_record_ids=[{}]),
            lambda o: o["tool_calls"][1].update(returned_record_ids=None),
            lambda o: o["tool_calls"][1].pop("returned_record_ids"),
            lambda o: o["tool_calls"][1].update(status=[]),
            lambda o: o.update(profile=None),
        ]
        for i, mutate in enumerate(mutations):
            o = self.observation(c)
            mutate(o)
            with self.subTest(mutation=i):
                self.assertFalse(grade(c, o)["structural_pass"])
        self.assertFalse(grade(c, None)["structural_pass"])

    def test_faults_and_matching_retry_are_required(self):
        for c in (self.cases[8], self.cases[11], self.cases[16]):
            o = self.observation(c)
            for call in o["tool_calls"]:
                if call["status"] == "unavailable":
                    call["status"] = "ok"
                    call["returned_record_ids"] = call["arguments"].get("record_ids", [])
            with self.subTest(case=c["case_id"]):
                self.assertFalse(grade(c, o)["structural_pass"])
        c = self.cases[11]
        o = self.observation(c)
        o["tool_calls"][1]["arguments"] = {"record_ids":["P012-R1"]}
        self.assertIn("missing_matching_retry", grade(c, o)["errors"])

    def test_empty_inventory_cannot_authorize_reads(self):
        c = self.cases[0]
        o = self.observation(c)
        o["tool_calls"][0]["status"] = "empty"
        self.assertIn("read_before_inventory", grade(c, o)["errors"])

    def test_empty_case_file_does_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.jsonl"
            path.write_text("")
            result = subprocess.run([sys.executable, str(Path(__file__).parent / "grade.py"),
                                     "--cases", str(path), "--observations", str(path)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("no evaluation was performed", result.stderr)

    def test_tool_result_schema_preserves_empty_and_failure_semantics(self):
        patient = json.loads((REPO_ROOT / self.cases[0]["patient_fixture"]).read_text())
        record = patient["records"][0]
        metadata = {k:v for k,v in record.items() if k != "content"}
        metadata["fact_keys"] = ["condition"]
        envelope = {"schema_version":"1.0","dataset_version":patient["dataset_version"],
                    "patient_id":patient["patient_id"],"status":"ok","error":None,
                    "data":{"records":[metadata],"inventory_complete":True}}
        list_schema = TOOLS["records__list_records"]["outputSchema"]
        self.assertEqual(validate(envelope, list_schema), [])
        envelope["status"] = "empty"
        self.assertTrue(validate(envelope, list_schema))
        envelope["data"]["records"] = []
        self.assertEqual(validate(envelope, list_schema), [])
        envelope["data"]["inventory_complete"] = False
        self.assertTrue(validate(envelope, list_schema))
        read_schema = TOOLS["records__read_records"]["outputSchema"]
        envelope.update(status="ok", data={"records":[record]})
        self.assertEqual(validate(envelope, read_schema), [])
        envelope["data"]["records"] = []
        self.assertTrue(validate(envelope, read_schema))
        envelope["status"] = "empty"
        self.assertTrue(validate(envelope, read_schema))
        envelope.update(status="denied", data=None, error={"code":"record_not_accessible","retryable":True})
        self.assertTrue(validate(envelope, read_schema))
        envelope["error"]["retryable"] = False
        self.assertEqual(validate(envelope, read_schema), [])
        for code, retryable in (("result_too_large",False),("record_unavailable",True)):
            envelope.update(status="unavailable", error={"code":code,"retryable":retryable})
            for schema in (list_schema, read_schema):
                self.assertEqual(validate(envelope, schema), [])
                envelope["error"]["retryable"] = not retryable
                self.assertTrue(validate(envelope, schema))
                envelope["error"]["retryable"] = retryable


if __name__ == "__main__":
    unittest.main()
