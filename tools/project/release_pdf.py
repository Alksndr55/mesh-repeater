"""Add invisible component-body hit targets to native KiCad schematic PDFs.

The native artwork and visible text are preserved. Existing text has priority
over the appended targets, so a pin or net label remains independently usable.
No editable schematic is written. The output replaces the PDF only after its
complete PDFium rendering and every added reference have been verified.
"""
from __future__ import annotations

import ctypes
import hashlib
from io import BytesIO
import math
import os
from pathlib import Path
import re
import sys

from circuit_io import children, one, properties, sexpr, value

sys.path.insert(0, str(Path(__file__).resolve().parent / 'vendor'))
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (ArrayObject, DecodedStreamObject, DictionaryObject,
                           FloatObject, NameObject, NumberObject)

PT_PER_MM = 72 / 25.4
FONT_NAME = '/MeshRepeaterBodyHit'
PAPER_MM = {'A0': (1189, 841), 'A1': (841, 594), 'A2': (594, 420),
            'A3': (420, 297), 'A4': (297, 210), 'A5': (210, 148)}


class PdfEnhancementError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise PdfEnhancementError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def point(item, key):
    entry = one(item, key)
    require(entry is not None and len(entry) == 3, 'Missing graphic point: ' + key)
    return float(entry[1]), float(entry[2])


def arc_points(item):
    """Endpoints, midpoint and the cardinal extrema of the actual circular arc."""
    a, b, c = [point(item, k) for k in ('start', 'mid', 'end')]
    ax, ay = a; bx, by = b; cx, cy = c
    d = 2 * (ax*(by-cy) + bx*(cy-ay) + cx*(ay-by))
    require(abs(d) > 1e-12, 'Degenerate symbol arc')
    aa, bb, cc = ax*ax+ay*ay, bx*bx+by*by, cx*cx+cy*cy
    ox = (aa*(by-cy)+bb*(cy-ay)+cc*(ay-by))/d
    oy = (aa*(cx-bx)+bb*(ax-cx)+cc*(bx-ax))/d
    radius = math.hypot(ax-ox, ay-oy)
    start, mid, end = [math.atan2(y-oy, x-ox) % math.tau for x,y in (a,b,c)]
    ccw = (mid-start) % math.tau <= (end-start) % math.tau
    points = [a,b,c]
    for angle in (0, math.pi/2, math.pi, math.pi*1.5):
        on_arc = ((angle-start) % math.tau <= (end-start) % math.tau + 1e-10
                  if ccw else (start-angle) % math.tau <= (start-end) % math.tau + 1e-10)
        if on_arc:
            points.append((ox+radius*math.cos(angle), oy+radius*math.sin(angle)))
    return points


def graphic_bounds(item):
    tag = item[0]
    if tag == 'rectangle':
        points = [point(item, 'start'), point(item, 'end')]
    elif tag == 'polyline':
        points = [tuple(map(float, xy[1:])) for xy in children(one(item, 'pts') or [], 'xy')]
    elif tag == 'circle':
        x,y = point(item, 'center')
        radius = float(one(item, 'radius')[1])
        require(radius > 0, 'Nonpositive symbol circle radius')
        points = [(x-radius,y-radius),(x+radius,y+radius)]
    elif tag == 'arc':
        points = arc_points(item)
    else:
        raise PdfEnhancementError('Unsupported symbol graphic: ' + tag)
    require(points, 'Empty symbol graphic: ' + tag)
    stroke = one(one(item, 'stroke') or [], 'width')
    width = float(stroke[1]) if stroke else 0
    # KiCad's zero/default pen width is 6 mil. This also gives line-only
    # symbols a nonzero hit rectangle, without extending to their pins.
    half_pen = (width if width > 0 else .1524) / 2
    return (min(p[0] for p in points)-half_pen, min(p[1] for p in points)-half_pen,
            max(p[0] for p in points)+half_pen, max(p[1] for p in points)+half_pen)


def body_bounds(symbol, library):
    at = one(symbol, 'at')
    require(at is not None and len(at) == 4 and float(at[3]) == 0,
            'Unverified rotated symbol transform')
    require(one(symbol, 'mirror') is None, 'Unverified mirrored symbol transform')
    require(one(library, 'extends') is None, 'Unresolved inherited symbol graphics')
    unit = int(one(symbol, 'unit')[1])
    require(unit == 1, 'Unverified multi-unit symbol')
    rectangles = []
    for part in children(library, 'symbol'):
        match = re.search(r'_(\d+)_(\d+)$', value(part[1]))
        require(match is not None, 'Unknown symbol body identity')
        part_unit, style = map(int, match.groups())
        if part_unit not in (0, unit) or style not in (0, 1):
            continue
        for graphic in part[2:]:
            if not isinstance(graphic, list) or graphic[0] == 'pin':
                continue
            rectangles.append(graphic_bounds(graphic))
    require(rectangles, 'Symbol has no physical body graphics')
    x,y = float(at[1]),float(at[2])
    # Library Y points up; sheet Y points down. Pins are deliberately absent.
    return (x+min(r[0] for r in rectangles), y-max(r[3] for r in rectangles),
            x+max(r[2] for r in rectangles), y-min(r[1] for r in rectangles))


def overlaps(a, b):
    return min(a[2],b[2])-max(a[0],b[0]) > 1e-6 and min(a[3],b[3])-max(a[1],b[1]) > 1e-6


def schematic_pages(schematic):
    root = Path(schematic).resolve()
    sources, pages, refs = {}, {}, set()

    def visit(path, number):
        path = path.resolve()
        require(path.parent == root.parent, 'Schematic sheet escapes native project')
        require(path not in sources and number not in pages, 'Repeated or cyclic schematic sheet')
        raw = path.read_bytes()
        sources[path] = sha(raw)
        tree = sexpr(raw.decode('utf-8-sig'))
        paper = one(tree, 'paper')
        require(paper is not None and value(paper[1]) in PAPER_MM, 'Unverified schematic paper size')
        size = PAPER_MM[value(paper[1])]
        if len(paper) > 2:
            require(paper[2:] == ['portrait'], 'Unsupported schematic paper transform')
            size = size[::-1]
        libraries = {value(s[1]): s for s in children(one(tree, 'lib_symbols') or [], 'symbol')}
        bodies = []
        for symbol in children(tree, 'symbol'):
            ref = properties(symbol).get('Reference', '')
            if ref.startswith('#'):
                continue
            require(re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', ref) is not None, 'Unverified reference: ' + ref)
            require(ref not in refs, 'Duplicate reference across schematic: ' + ref)
            refs.add(ref)
            lib_id = value(one(symbol, 'lib_id')[1])
            require(lib_id in libraries, 'Missing native symbol: ' + lib_id)
            box = body_bounds(symbol, libraries[lib_id])
            require(0 <= box[0] < box[2] <= size[0] and 0 <= box[1] < box[3] <= size[1],
                    'Symbol body outside sheet: ' + ref)
            for other in bodies:
                require(not overlaps(box, other['body_mm']),
                        'Overlapping symbol bodies: ' + ref + '/' + other['reference'])
            bodies.append({'reference': ref, 'body_mm': box})
        pages[number] = {'source': path, 'paper_mm': size, 'bodies': bodies}
        for sheet in children(tree, 'sheet'):
            filename = properties(sheet).get('Sheetfile')
            page_numbers = {int(value(n[1])) for p in children(one(sheet, 'instances') or [], 'project')
                            for q in children(p, 'path') for n in children(q, 'page')}
            require(filename and len(page_numbers) == 1, 'Ambiguous native sheet/page mapping')
            visit(path.parent / filename, page_numbers.pop())

    root_tree = sexpr(root.read_text('utf-8-sig'))
    root_numbers = {int(value(n[1])) for p in children(one(root_tree, 'sheet_instances') or [], 'path')
                    for n in children(p, 'page')}
    require(root_numbers == {1}, 'Unverified root sheet page number')
    visit(root, 1)
    require(set(pages) == set(range(1, len(pages)+1)), 'Non-contiguous PDF page mapping')
    return pages, sources


def add_body_font(writer, page, references):
    """A rectangle glyph gives every point in a character cell a hit box."""
    # Native pages share a font dictionary. Give this page its own resource
    # mapping, preserving all original font objects and their byte content.
    resources = DictionaryObject(dict(page['/Resources'].get_object()))
    existing = resources.get('/Font', DictionaryObject()).get_object()
    fonts = DictionaryObject(dict(existing))
    require(FONT_NAME not in fonts, 'PDF already contains component-body targets')
    resources[NameObject('/Font')] = fonts
    page[NameObject('/Resources')] = resources
    glyph = DecodedStreamObject()
    glyph.set_data(b'1000 0 0 0 1000 1000 d1\n0 0 1000 1000 re f\n')
    glyph_ref = writer._add_object(glyph)
    codes = sorted(set(ord(c) for ref in references for c in ref))
    names = [(c, '/uni%04X' % c) for c in codes]
    cmap = DecodedStreamObject()
    cmap.set_data(('/CIDInit /ProcSet findresource begin\n12 dict begin begincmap\n'
        '/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n'
        '/CMapName /MeshRepeaterBodyHitUnicode def /CMapType 2 def\n'
        '1 begincodespacerange <00> <FF> endcodespacerange\n'
        + str(len(codes)) + ' beginbfchar\n' + '\n'.join('<%02X> <%04X>' % (c,c) for c in codes)
        + '\nendbfchar\nendcmap CMapName currentdict /CMap defineresource pop end end\n').encode('ascii'))
    font = DictionaryObject({NameObject('/Type'):NameObject('/Font'),
        NameObject('/Subtype'):NameObject('/Type3'),
        NameObject('/FontBBox'):ArrayObject([NumberObject(x) for x in (0,0,1000,1000)]),
        NameObject('/FontMatrix'):ArrayObject([FloatObject(x) for x in (.001,0,0,.001,0,0)]),
        NameObject('/CharProcs'):DictionaryObject({NameObject(n):glyph_ref for _,n in names}),
        NameObject('/Encoding'):DictionaryObject({NameObject('/Type'):NameObject('/Encoding'),
            NameObject('/Differences'):ArrayObject([v for c,n in names for v in (NumberObject(c),NameObject(n))])}),
        NameObject('/FirstChar'):NumberObject(min(codes)), NameObject('/LastChar'):NumberObject(max(codes)),
        NameObject('/Widths'):ArrayObject([NumberObject(1000)]*(max(codes)-min(codes)+1)),
        NameObject('/Resources'):DictionaryObject(), NameObject('/ToUnicode'):writer._add_object(cmap)})
    fonts[NameObject(FONT_NAME)] = writer._add_object(font)


def load_pdfium():
    path = Path(__file__).resolve().parents[2] / 'third_party/NexusBV/0.9/pdfium.dll'
    require(os.name == 'nt' and path.is_file(), 'Bundled Windows PDFium is required for PDF render verification')
    directory = os.add_dll_directory(str(path.parent))
    try:
        dll = ctypes.CDLL(str(path))
    finally:
        directory.close()
    pointer, integer, double = ctypes.c_void_p, ctypes.c_int, ctypes.c_double
    signatures = {
        'FPDF_InitLibrary': (None, []), 'FPDF_DestroyLibrary': (None, []),
        'FPDF_LoadMemDocument64': (pointer, [pointer,ctypes.c_size_t,ctypes.c_char_p]),
        'FPDF_CloseDocument': (None,[pointer]), 'FPDF_GetPageCount': (integer,[pointer]),
        'FPDF_LoadPage': (pointer,[pointer,integer]), 'FPDF_ClosePage': (None,[pointer]),
        'FPDF_GetPageWidth': (double,[pointer]), 'FPDF_GetPageHeight': (double,[pointer]),
        'FPDFBitmap_Create': (pointer,[integer,integer,integer]),
        'FPDFBitmap_FillRect': (None,[pointer,integer,integer,integer,integer,ctypes.c_uint]),
        'FPDF_RenderPageBitmap': (None,[pointer,pointer,integer,integer,integer,integer,integer,integer]),
        'FPDFBitmap_GetBuffer': (pointer,[pointer]), 'FPDFBitmap_GetStride': (integer,[pointer]),
        'FPDFBitmap_Destroy': (None,[pointer]),
        'FPDFText_LoadPage': (pointer,[pointer]), 'FPDFText_ClosePage': (None,[pointer]),
        'FPDFText_CountChars': (integer,[pointer]), 'FPDFText_GetUnicode': (ctypes.c_uint,[pointer,integer]),
        'FPDFText_GetCharBox': (integer,[pointer,integer,*([ctypes.POINTER(double)]*4)]),
        'FPDFText_GetCharIndexAtPos': (integer,[pointer,double,double,double,double]),
    }
    for name,(result,args) in signatures.items():
        fn = getattr(dll,name)
        fn.restype,fn.argtypes = result,args
    return dll


def verify_pdf_render(original, enhanced, regions):
    dll = load_pdfium()
    buffers = [ctypes.create_string_buffer(raw) for raw in (original,enhanced)]
    docs = []
    proof = []
    dll.FPDF_InitLibrary()
    try:
        for buf,raw in zip(buffers,(original,enhanced)):
            doc = dll.FPDF_LoadMemDocument64(buf,len(raw),None)
            require(doc, 'PDFium cannot load schematic PDF')
            docs.append(doc)
        count = dll.FPDF_GetPageCount(docs[0])
        require(count == dll.FPDF_GetPageCount(docs[1]), 'PDF page count changed')
        for index in range(count):
            pages = [dll.FPDF_LoadPage(doc,index) for doc in docs]
            try:
                require(all(pages), 'PDFium cannot load schematic page')
                rendered = []
                for page in pages:
                    w,h = [math.ceil(v*2) for v in (dll.FPDF_GetPageWidth(page),dll.FPDF_GetPageHeight(page))]
                    bitmap = dll.FPDFBitmap_Create(w,h,1)
                    require(bitmap, 'PDFium cannot allocate verification bitmap')
                    try:
                        dll.FPDFBitmap_FillRect(bitmap,0,0,w,h,0xFFFFFFFF)
                        dll.FPDF_RenderPageBitmap(bitmap,page,0,0,w,h,0,0)
                        raw = ctypes.string_at(dll.FPDFBitmap_GetBuffer(bitmap),dll.FPDFBitmap_GetStride(bitmap)*h)
                        rendered.append((w,h,sha(raw)))
                    finally:
                        dll.FPDFBitmap_Destroy(bitmap)
                require(rendered[0] == rendered[1], 'PDF artwork changed on page ' + str(index+1))
                textpage = dll.FPDFText_LoadPage(pages[1])
                require(textpage, 'PDFium cannot read verification text')
                try:
                    chars = []
                    for i in range(dll.FPDFText_CountChars(textpage)):
                        left,right,bottom,top = [ctypes.c_double() for _ in range(4)]
                        if dll.FPDFText_GetCharBox(textpage,i,ctypes.byref(left),ctypes.byref(right),ctypes.byref(bottom),ctypes.byref(top)):
                            chars.append((i,dll.FPDFText_GetUnicode(textpage,i),(left.value,bottom.value,right.value,top.value)))
                    verified = []
                    for region in regions.get(index+1,[]):
                        x0,y0,x1,y1 = region['body_pdf']
                        ref = region['reference']; step = (x1-x0)/len(ref)
                        added = set()
                        for j,c in enumerate(ref):
                            expected = (x0+j*step,y0,x0+(j+1)*step,y1)
                            matches = [i for i,code,box in chars if code==ord(c) and max(abs(a-b) for a,b in zip(expected,box)) < .02]
                            require(len(matches)==1, 'Missing or ambiguous PDF body text: ' + ref)
                            added.update(matches)
                        hits = 0
                        for fx in (.1,.3,.5,.7,.9):
                            for fy in (.1,.5,.9):
                                i = dll.FPDFText_GetCharIndexAtPos(textpage,x0+(x1-x0)*fx,y0+(y1-y0)*fy,0,0)
                                hits += i in added
                        require(hits > 0, 'Body entirely covered by existing text: ' + ref)
                        verified.append({'reference':ref,'body_hit_samples':hits,'samples':15})
                    proof.append({'page':index+1,'render_144dpi_identical':True,
                                  'render_sha256':rendered[0][2], 'body_targets':verified})
                finally:
                    dll.FPDFText_ClosePage(textpage)
            finally:
                for page in pages:
                    if page:
                        dll.FPDF_ClosePage(page)
        return proof
    finally:
        for doc in docs:
            dll.FPDF_CloseDocument(doc)
        dll.FPDF_DestroyLibrary()


def enhance_schematic_pdf(schematic_path, pdf_path):
    schematic, pdf = Path(schematic_path).resolve(),Path(pdf_path).resolve()
    pages,sources = schematic_pages(schematic)
    original = pdf.read_bytes()
    reader = PdfReader(BytesIO(original))
    require(len(reader.pages)==len(pages), 'PDF/native sheet count mismatch')
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    regions = {}
    for number,native in sorted(pages.items()):
        page = writer.pages[number-1]
        require(int(page.get('/Rotate',0))==0 and float(page.get('/UserUnit',1))==1,
                'Unverified PDF page transform')
        w,h = float(page.mediabox.width),float(page.mediabox.height)
        require(abs(w-native['paper_mm'][0]*PT_PER_MM)<.1 and abs(h-native['paper_mm'][1]*PT_PER_MM)<.1,
                'PDF/native sheet dimensions mismatch')
        require(tuple(page.cropbox)==tuple(page.mediabox) and float(page.mediabox.left)==0 and float(page.mediabox.bottom)==0,
                'Unverified PDF crop or origin')
        if not native['bodies']:
            continue
        fragments = []
        page.extract_text(visitor_text=lambda text, *_: fragments.append(text))
        # KiCad puts references and values in adjacent text objects; paragraph
        # extraction can join R5 + 1M into R51M. Inspect text objects separately.
        visible_refs = {token for fragment in fragments for token in
                        re.findall(r'(?<![A-Za-z0-9_])[A-Za-z][A-Za-z0-9_]*(?![A-Za-z0-9_])',fragment)}
        for body in native['bodies']:
            require(body['reference'] in visible_refs,
                    'Reference missing from native PDF page: ' + body['reference'])
        add_body_font(writer,page,[body['reference'] for body in native['bodies']])
        stream = []
        regions[number] = []
        for body in native['bodies']:
            left,top,right,bottom = body['body_mm']
            x0,y0,x1,y1 = left*PT_PER_MM,h-bottom*PT_PER_MM,right*PT_PER_MM,h-top*PT_PER_MM
            ref = body['reference']; height = y1-y0
            horizontal = 100*(x1-x0)/(len(ref)*height)
            stream.append(f'q BT {FONT_NAME} {height:.9f} Tf {horizontal:.9f} Tz 3 Tr 1 0 0 1 {x0:.9f} {y0:.9f} Tm ({ref}) Tj ET Q\n')
            regions[number].append({'reference':ref,'body_pdf':[x0,y0,x1,y1]})
        target = DecodedStreamObject()
        target.set_data(''.join(stream).encode('ascii'))
        old = page.get('/Contents')
        old = old.get_object() if old is not None else None
        contents = list(old) if isinstance(old,ArrayObject) else ([page.raw_get('/Contents')] if old is not None else [])
        # Native KiCad streams may leave their final text/drawing matrix active.
        # Isolate the original content before appending sheet-coordinate targets.
        before = DecodedStreamObject(); before.set_data(b'q\n')
        after = DecodedStreamObject(); after.set_data(b'Q\n')
        # Preserve existing text's hit-testing priority, including pin labels.
        page[NameObject('/Contents')] = ArrayObject([writer._add_object(before),*contents,
            writer._add_object(after),writer._add_object(target)])
    output = BytesIO()
    writer.write(output)
    enhanced = output.getvalue()
    visual_proof = verify_pdf_render(original,enhanced,regions)
    require(all(sha(path.read_bytes())==expected for path,expected in sources.items()), 'Schematic changed during PDF export')
    require(pdf.read_bytes()==original, 'PDF changed during body-target export')
    temporary = pdf.with_name(pdf.name+'.body-targets.tmp')
    try:
        temporary.write_bytes(enhanced)
        temporary.replace(pdf)
    finally:
        if temporary.exists():
            temporary.unlink()
    return {'status':'PASS','format':'KiCad PDF with invisible component-body text',
            'native_pdf_sha256':sha(original),'pdf_sha256':sha(enhanced),
            'schematic_sha256':{str(p):s for p,s in sorted(sources.items())},
            'components':sum(len(v) for v in regions.values()),'pages':len(pages),
            'body_regions':regions,'verification':visual_proof,
            'original_text_has_priority':True,'schematics_unchanged':True,
            'scope':'Body graphics only; existing text, pin labels and net names retain their original hit priority.'}
