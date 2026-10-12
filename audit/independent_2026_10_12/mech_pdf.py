from pathlib import Path
import pdfplumber, json
root=Path.cwd();out=root/'audit/independent_2026_10_12'
pdfs=[root/'docs/mechanical_sources/DS1022.pdf',root/'docs/mechanical_sources/DS1016.pdf',root/'docs/mechanical_sources/167075.pdf',out/'mech_DS1027.pdf']
for p in pdfs:
 with pdfplumber.open(p) as doc:
  print('\n'+p.name+' '+str(len(doc.pages))+' pages')
  print(doc.pages[0].extract_text()[:4000])
  if 'DS1027' in p.name:doc.pages[0].to_image(resolution=130).save(str(out/'mech_DS1027.png'))
