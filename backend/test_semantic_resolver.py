"""Tests for the Ninko evidence semantic resolver."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.evidence import GlossaryEntry, GlossaryStore, SemanticResolver, field_mapping_confidence
from core.evidence.module_semantic_index import ModuleSemanticDocument, ModuleSemanticIndex


class TestSemanticResolver(unittest.TestCase):
    def test_semantically_equivalent_term_routes_to_glossary_module(self):
        resolver = SemanticResolver(
            glossary=GlossaryStore.with_defaults(),
            module_index=ModuleSemanticIndex([
                ModuleSemanticDocument(
                    name="postgresql",
                    text="postgresql database sql invoice storage faktura",
                ),
            ]),
        )

        result = resolver.resolve("Fakturaverarbeitung blockiert")

        self.assertIn("postgresql", result.candidate_modules)
        self.assertTrue(any(r.term == "fakturaverarbeitung" for r in result.resolutions))
        postgresql_resolution = next(
            r for r in result.resolutions if r.term == "fakturaverarbeitung"
        )
        self.assertEqual(postgresql_resolution.source_module, "postgresql")
        self.assertEqual(postgresql_resolution.confidence, "high")

    def test_unknown_term_sets_explicit_escalation(self):
        resolver = SemanticResolver(
            glossary=GlossaryStore([]),
            module_index=ModuleSemanticIndex([]),
        )

        result = resolver.resolve("xqznotion drift prüfen")

        self.assertTrue(result.escalation_required)
        self.assertIn("xqznotion", result.unresolved_terms)
        self.assertIsNotNone(result.escalation_reason)

    def test_explicit_candidate_module_name_does_not_escalate(self):
        resolver = SemanticResolver(
            glossary=GlossaryStore([]),
            module_index=ModuleSemanticIndex([]),
        )

        result = resolver.resolve(
            "licium Lies meine bestehenden Notizen und ingeste sie ins Ninko-Wiki",
            candidate_modules=["licium"],
        )

        self.assertFalse(result.escalation_required)
        self.assertEqual(result.unresolved_terms, [])
        self.assertIn("licium", result.candidate_modules)

    def test_field_mapping_outputs_confidence_for_heterogeneous_names(self):
        resolution = field_mapping_confidence("GP_Id", "businesspartner_id")

        self.assertEqual(resolution.resolved_to, "business_partner_id")
        self.assertIn(resolution.confidence, {"uncertain", "high"})
        self.assertGreater(resolution.score, 0.0)

    def test_custom_glossary_entry_resolves_module(self):
        resolver = SemanticResolver(
            glossary=GlossaryStore([
                GlossaryEntry(
                    canonical="invoice",
                    aliases=["rechnung", "faktura"],
                    module="erp",
                    field="invoice_id",
                )
            ]),
            module_index=ModuleSemanticIndex([]),
        )

        result = resolver.resolve("Rechnung prüfen")

        self.assertIn("erp", result.candidate_modules)
        self.assertEqual(result.resolutions[0].resolved_to, "invoice_id")


if __name__ == "__main__":
    unittest.main()
