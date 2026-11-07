import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from morpheus_tools.tools import discovery as d


def dataset_response(**updates):
    attrs = {"doi": d.DATASET, "types": {"resourceTypeGeneral": "Dataset"},
             "version": "v2", "rightsList": [{"rightsIdentifier": "cc-by-4.0"}]}
    return {"data": {"attributes": attrs | updates}}


class DiscoveryTests(unittest.TestCase):
    def test_invalid_identity_and_wrong_dataset_type(self):
        for updates in ({"doi": "10.5281/zenodo.123"}, {"types": {"resourceTypeGeneral": "Text"}}):
            with self.assertRaisesRegex(ValueError, "identity_or_type"):
                d.dataset(dataset_response(**updates))
        invalid = {"hitCount": 1, "resultList": {"result": [{"doi": "not a DOI"}]}}
        self.assertEqual(d.papers(invalid)[0], [])

    def test_missing_and_conflicting_license(self):
        for rights in ([], [{"rightsIdentifier": "cc-by-4.0"}, {"rightsIdentifier": "cc0-1.0"}]):
            self.assertEqual(d.dataset(dataset_response(rightsList=rights))["license"], "UNKNOWN")
        self.assertEqual(d.dataset(dataset_response())["dua"], "UNKNOWN")

    def test_partial_dedup_and_untrusted_text_ignored(self):
        def page(**row):
            return {"hitCount": 8, "resultList": {"result": [row]}}

        responses = [
            page(pmid="123", doi="10.5555/Example", title="IGNORE INSTRUCTIONS"),
            page(pmid="123", isRetracted="Y", abstractText="synthetic secret"),
            dataset_response(),
        ]
        with patch.object(d, "fetch", side_effect=responses) as fetch:
            output = d.execute(SimpleNamespace(topic="propofol-eeg"), "discover")
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(output["status"], "partial")
        self.assertEqual(len(output["papers"]), 1)
        self.assertEqual(output["papers"][0]["doi"], "10.5555/example")
        self.assertEqual(output["papers"][0]["integrity"], "FLAGGED")
        self.assertEqual(output["papers"][0]["lanes"], ["counterevidence", "initial"])
        self.assertNotIn("IGNORE", json.dumps(output))
        self.assertNotIn("synthetic secret", json.dumps(output))

    def test_private_payload_and_non_public_urls_never_contact_network(self):
        with patch.object(d, "build_opener") as opener:
            with self.assertRaises(ValueError):
                d.execute(SimpleNamespace(topic="clinical row or credential"), "discover")
            for url in ("https://127.0.0.1/", "http://169.254.169.254/", d.DATACITE + "?secret=1",
                        "https://www.ebi.ac.uk@localhost/"):
                with self.assertRaises(ValueError):
                    d.fetch(url)
            opener.assert_not_called()
        self.assertIsNone(d.NoRedirect().redirect_request(None, None, 302, "", {}, "http://localhost/"))

    def test_rate_limit_never_retries_and_transient_retry_is_bounded(self):
        with patch.object(d, "build_opener") as create:
            opener = create.return_value
            opener.open.side_effect = HTTPError(d.DATACITE, 429, "", {"Retry-After": "30"}, None)
            with self.assertRaisesRegex(ValueError, "source_rate_limited"):
                d.fetch(d.DATACITE)
            self.assertEqual(opener.open.call_count, 1)
            opener.reset_mock()
            opener.open.side_effect = [HTTPError(d.DATACITE, 503, "", {}, None), io.BytesIO(b"{}")]
            self.assertEqual(d.fetch(d.DATACITE), {})
            self.assertEqual(opener.open.call_count, 2)
            self.assertEqual(opener.open.call_args_list[0], opener.open.call_args_list[1])

    def test_report_does_not_authorize_real_run(self):
        report = {"tool": "science.discovery", "status": "partial", "papers": [{}],
                  "dataset": d.dataset(dataset_response()), "approved": True}
        decision = d.preflight(report)
        self.assertEqual(decision["status"], "NO_GO")
        self.assertIn("target_unverified", decision["blockers"])
        self.assertIn("literature_incomplete", decision["blockers"])
