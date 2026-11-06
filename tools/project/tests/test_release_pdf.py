"""Proof for body-target placement, transform isolation, and atomic rejection."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from circuit_io import sexpr
from release_pdf import (PdfEnhancementError, PT_PER_MM, body_bounds, graphic_bounds,
                         schematic_pages, enhance_schematic_pdf)
from pypdf import PdfWriter, PdfReader
from pypdf.generic import (DictionaryObject, NameObject, DecodedStreamObject)

LIBRARY = '''(symbol "Fixture:R" (symbol "R_0_1"
  (rectangle (start -2 1) (end 2 -1) (stroke (width 0.2))))
  (symbol "R_1_1" (pin passive line (at -20 0 0) (length 18))))'''


class PdfBodyTargetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def schematic(self, extra='', symbol_at='50 50 0'):
        path = self.folder / 'fixture.kicad_sch'
        path.write_text('''(kicad_sch (paper "A4") (lib_symbols '''+LIBRARY+''')
          (symbol (lib_id "Fixture:R") (at '''+symbol_at+''') (unit 1)
            (property "Reference" "R1")) '''+extra+'''
          (sheet_instances (path "/" (page "1"))))''', 'utf-8')
        return path

    def pdf(self):
        path = self.folder / 'fixture.pdf'
        writer = PdfWriter()
        page = writer.add_blank_page(297*PT_PER_MM,210*PT_PER_MM)
        font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),
            NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):
            DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        content = DecodedStreamObject()
        # The final unbalanced coordinate transform reproduces native KiCad's
        # inherited-CTM bug: appending targets without outer q/Q misses the body.
        content.set_data(b'BT /F1 5 Tf 1 0 0 1 136 467 Tm (R1) Tj ET\n'
                         b'BT /F1 5 Tf 1 0 0 1 142.39 467 Tm (10k) Tj ET\n'
                         b'0.2 w 136.063 450.709 11.339 5.669 re S\n2 0 0 2 500 500 cm\n')
        page[NameObject('/Contents')] = writer._add_object(content)
        with path.open('wb') as stream:
            writer.write(stream)
        return path

    def test_body_excludes_far_pin_and_contains_stroke(self):
        symbol = sexpr('(symbol (at 50 50 0) (unit 1))')
        self.assertEqual(body_bounds(symbol,sexpr(LIBRARY)),(47.9,48.9,52.1,51.1))

    def test_unverified_transforms_fail_closed(self):
        for fields in ('(at 50 50 90) (unit 1)', '(at 50 50 0) (unit 1) (mirror x)',
                       '(at 50 50 0) (unit 2)'):
            with self.subTest(fields=fields), self.assertRaises(PdfEnhancementError):
                body_bounds(sexpr('(symbol '+fields+')'),sexpr(LIBRARY))

    def test_arc_bound_uses_true_extrema(self):
        box = graphic_bounds(sexpr('(arc (start 1 0) (mid 0 1) (end -1 0) (stroke (width 0.2)))'))
        for got,want in zip(box,(-1.1,-.1,1.1,1.1)):
            self.assertAlmostEqual(got,want)

    def test_native_mapping_and_overlap_guard(self):
        pages,_ = schematic_pages(self.schematic())
        self.assertEqual(pages[1]['bodies'][0]['reference'],'R1')
        extra='(symbol (lib_id "Fixture:R") (at 50 50 0) (unit 1) (property "Reference" "R2"))'
        with self.assertRaisesRegex(PdfEnhancementError,'Overlapping'):
            schematic_pages(self.schematic(extra))

    def test_real_pdfium_render_and_hit_target_after_leaked_transform(self):
        sch,pdf = self.schematic(),self.pdf()
        source = sch.read_bytes()
        result = enhance_schematic_pdf(sch,pdf)
        self.assertEqual(result['status'],'PASS')
        self.assertEqual(result['components'],1)
        self.assertTrue(result['verification'][0]['render_144dpi_identical'])
        self.assertEqual(result['verification'][0]['body_targets'][0]['body_hit_samples'],15)
        self.assertEqual(sch.read_bytes(),source)
        self.assertIn('R1',PdfReader(pdf).pages[0].extract_text())
        with self.assertRaisesRegex(PdfEnhancementError,'already contains'):
            enhance_schematic_pdf(sch,pdf)

    def test_reference_adjacent_to_value_uses_text_objects(self):
        sch,pdf = self.schematic(),self.pdf()
        self.assertIn('R110k',PdfReader(pdf).pages[0].extract_text())
        self.assertEqual(enhance_schematic_pdf(sch,pdf)['components'],1)

    def test_shared_original_font_dictionary_does_not_share_body_font(self):
        sch,pdf = self.schematic(),self.pdf()
        child = self.folder / 'child.kicad_sch'
        child.write_text(sch.read_text('utf-8').replace('"R1"','"R2"'),'utf-8')
        sch = self.schematic(extra='''(sheet (property "Sheetfile" "child.kicad_sch")
          (instances (project "fixture" (path "/root" (page "2")))))''')
        writer = PdfWriter(); writer.clone_document_from_reader(PdfReader(pdf))
        first = writer.pages[0]
        shared_fonts = writer._add_object(first['/Resources']['/Font'])
        first['/Resources'][NameObject('/Font')] = shared_fonts
        second = writer.add_blank_page(297*PT_PER_MM,210*PT_PER_MM)
        second[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'):shared_fonts})
        content = DecodedStreamObject()
        content.set_data(first.get_contents().get_data().replace(b'(R1)',b'(R2)'))
        second[NameObject('/Contents')] = writer._add_object(content)
        with pdf.open('wb') as stream:
            writer.write(stream)
        result = enhance_schematic_pdf(sch,pdf)
        self.assertEqual(result['components'],2)
        self.assertEqual(result['pages'],2)
        self.assertTrue(all(p['render_144dpi_identical'] for p in result['verification']))

    def test_failed_render_preserves_original_pdf(self):
        sch,pdf = self.schematic(),self.pdf()
        original = pdf.read_bytes()
        with patch('release_pdf.verify_pdf_render',side_effect=PdfEnhancementError('visual change')):
            with self.assertRaisesRegex(PdfEnhancementError,'visual change'):
                enhance_schematic_pdf(sch,pdf)
        self.assertEqual(pdf.read_bytes(),original)

    def test_changed_schematic_rejects_without_replacing_pdf(self):
        sch,pdf = self.schematic(),self.pdf()
        original = pdf.read_bytes()
        def mutate(*args):
            sch.write_text(sch.read_text('utf-8')+'\n','utf-8')
            return []
        with patch('release_pdf.verify_pdf_render',side_effect=mutate):
            with self.assertRaisesRegex(PdfEnhancementError,'Schematic changed'):
                enhance_schematic_pdf(sch,pdf)
        self.assertEqual(pdf.read_bytes(),original)


if __name__ == '__main__':
    unittest.main()
