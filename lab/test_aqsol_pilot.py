import importlib.util
import unittest

from aqsol_pilot import descriptor_record, partition_facts


class AqSolPreparationTests(unittest.TestCase):
    def test_group_and_identity_gates(self):
        rows = [[f"id-{i}", f"group-{i // 15}", [0.0] * 9, 0.0] for i in range(1500)]
        facts = partition_facts({"train": rows[:1200], "test": rows[1200:]})
        self.assertEqual((facts["test_fraction"], facts["identity_overlap"], facts["scaffold_overlap"]),
                         (0.2, 0, 0))
        with self.assertRaisesRegex(ValueError, "aqsol_frozen_split_gate_failed"):
            partition_facts({"train": rows[:1199], "test": rows[1199:]})
        with self.assertRaisesRegex(ValueError, "aqsol_frozen_split_gate_failed"):
            partition_facts({"train": rows[:1350], "test": rows[1350:]})
        with self.assertRaisesRegex(ValueError, "aqsol_frozen_split_gate_failed"):
            partition_facts({"train": rows[:1200], "test": [rows[0], *rows[1201:]]})

    @unittest.skipUnless(importlib.util.find_spec("rdkit"), "requires pinned RDKit")
    def test_descriptors_use_only_one_resolved_ring_structure(self):
        self.assertEqual(descriptor_record("CCO")[0], "acyclic")
        self.assertEqual(descriptor_record("c1ccccc1.[Na+]")[0], "multiple_fragments")
        self.assertEqual(descriptor_record("not-a-smiles")[0], "invalid_smiles")
        self.assertEqual(descriptor_record("CC(O)c1ccccc1")[0], "unresolved_stereochemistry")
        reason, record = descriptor_record("c1ccccc1O")
        self.assertIsNone(reason)
        self.assertEqual(record[1], "c1ccccc1")
        self.assertEqual(len(record[2]), 9)
