"""Render edited PDFs for review. No visual-pass assertion until root inspection."""
from pathlib import Path
import hashlib, json, subprocess, sys
from pypdf import PdfReader
from PIL import Image, ImageOps, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
name = sys.argv[1]
files = {
    'manual': ROOT/'output/pdf/MeshRepeater2_assembly_manual_RU.pdf',
    'dimensions': ROOT/'output/pdf/MeshRepeater2_assembly_dimensions.pdf',
    'power_schematic': ROOT/'output/pdf/MeshRepeater2_Power_schematic.pdf',
    'logic_schematic': ROOT/'output/pdf/MeshRepeater2_Logic_schematic.pdf',
}
pdf = files[name]
dest = OUT/('pdf_' + name)
dest.mkdir(exist_ok=True)
subprocess.run(['pdftoppm', '-r', '110', '-png', str(pdf), str(dest/'page')], check=True)
reader = PdfReader(pdf)
pages = []
thumbnails = []
for n, (page, png) in enumerate(zip(reader.pages, sorted(dest.glob('page-*.png'))), 1):
    text = page.extract_text()
    (dest/f'page-{n}.txt').write_text(text, encoding='utf-8')
    im = Image.open(png).convert('RGB')
    thumb = ImageOps.contain(im, (440, 650))
    tile = Image.new('RGB', (460, 685), 'white')
    tile.paste(thumb, ((460-thumb.width)//2, 25))
    ImageDraw.Draw(tile).text((12, 8), f'{name} {n}', fill='black')
    thumbnails.append(tile)
    pages.append({'page':n, 'text_characters':len(text), 'image':str(png.relative_to(ROOT)), 'image_sha256':hashlib.sha256(png.read_bytes()).hexdigest()})
cols = 3 if name == 'manual' else 2
sheet = Image.new('RGB', (460*cols, 685*((len(thumbnails)+cols-1)//cols)), '#d5dce3')
for i, tile in enumerate(thumbnails):
    sheet.paste(tile, ((i%cols)*460, (i//cols)*685))
sheet.save(dest/'contact_sheet.png')
data = {'pdf':{'path':str(pdf.relative_to(ROOT)), 'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}, 'page_count':len(reader.pages), 'rendered_pages':pages, 'pending_visual_inspection':True}
(OUT/('root_pdf_' + name + '.json')).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'pdf':str(pdf.relative_to(ROOT)), 'pages':len(reader.pages), 'characters':[p['text_characters'] for p in pages], 'contact_sheet':str(dest/'contact_sheet.png')}))
