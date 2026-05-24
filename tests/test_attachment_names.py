import unittest

from stdlib.text_normalize import attachment_name_for_pdf


class AttachmentNameForPdfTests(unittest.TestCase):
    def test_strips_pdf_extension(self):
        self.assertEqual(attachment_name_for_pdf("a.pdf"), "a")

    def test_strips_case_insensitive_extension(self):
        self.assertEqual(attachment_name_for_pdf("КП_Билайн.PDF"), "КП_Билайн")

    def test_strips_jpg(self):
        self.assertEqual(attachment_name_for_pdf("фото_1.jpg"), "фото_1")

    def test_multi_dot_stem(self):
        self.assertEqual(attachment_name_for_pdf("a.b.c.pdf"), "a.b.c")

    def test_no_extension_unchanged(self):
        name = "Протокол сравнительного анализа"
        self.assertEqual(attachment_name_for_pdf(name), name)

    def test_empty_returns_file(self):
        self.assertEqual(attachment_name_for_pdf(""), "Файл")
        self.assertEqual(attachment_name_for_pdf("   "), "Файл")

    def test_strips_path_if_present(self):
        self.assertEqual(attachment_name_for_pdf("dir/doc.pdf"), "doc")


if __name__ == "__main__":
    unittest.main()
