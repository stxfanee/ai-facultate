import tempfile
import unittest
from pathlib import Path

from pypdf import PdfWriter

import app
from user_accounts import UserAccountStore, user_context, workspace_context


class PdfViewerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.original_accounts = app.USER_ACCOUNTS
        app.USER_ACCOUNTS = UserAccountStore(self.root / "storage")
        app.USER_ACCOUNTS.create_profile("ana")
        app.USER_ACCOUNTS.create_workspace("ana", "Biochimie")

    def tearDown(self):
        app.USER_ACCOUNTS = self.original_accounts
        self.temporary_directory.cleanup()

    @staticmethod
    def write_pdf(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        writer = PdfWriter()
        writer.add_blank_page(width=612, height=792)
        with path.open("wb") as output:
            writer.write(output)

    def test_pdf_resolution_is_restricted_to_current_workspace(self):
        general = app.USER_ACCOUNTS.workspace("ana", "general").documents / "general.pdf"
        bio = app.USER_ACCOUNTS.workspace("ana", "biochimie").documents / "bio.pdf"
        self.write_pdf(general)
        self.write_pdf(bio)

        with user_context("ana"), workspace_context("biochimie"):
            self.assertEqual(app.resolve_workspace_pdf("bio.pdf"), bio.resolve())
            self.assertIsNone(app.resolve_workspace_pdf("general.pdf", str(general)))
            self.assertIsNone(app.resolve_workspace_pdf("../general.pdf"))

    def test_pdf_text_layer_reports_page_count(self):
        pdf_path = self.root / "blank.pdf"
        self.write_pdf(pdf_path)
        layer = app.extract_pdf_text_layer(str(pdf_path), pdf_path.stat().st_mtime_ns)
        self.assertEqual(layer["page_count"], 1)
        self.assertEqual(len(layer["pages"]), 1)

    def test_citation_records_keep_excerpt_for_highlighting(self):
        response = app.StudyResponse(
            "answer",
            [
                {
                    "text": "Paragraful citat despre glicoliză.",
                    "rerank_score": 0.9,
                    "metadata": {
                        "file_name": "Biochimie.pdf",
                        "page_number": 7,
                    },
                }
            ],
            {},
        )
        source = app.response_source_records(response)[0]
        self.assertEqual(source["page"], 7)
        self.assertIn("glicoliză", source["excerpt"])


if __name__ == "__main__":
    unittest.main()
