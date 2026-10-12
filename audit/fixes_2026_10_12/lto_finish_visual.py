from pathlib import Path
p = Path(__file__).with_name('lto_proposal.py')
s = p.read_text(encoding='utf-8')
first = s.index("svg = '''<svg")
marker = s.find('# A deliberately simple clean connection diagram', first)
if marker != -1:
    s = s[:first] + s[marker:]
s = s.replace('<text x="670" y="278" class="s">CCOMP · 100nF</text>', '<text x="705" y="250" class="s">CCOMP · 100nF</text>')
s = s.replace('<text x="520" y="396">RB · 390 Ω</text>', '<text x="590" y="396">RB · 390 Ω</text>')
s = s.replace('<text x="870" y="430">BCX53-16,115</text><text x="880" y="454" class="s">SOT89 · QBOOST</text>', '<text x="960" y="470">BCX53-16,115</text><text x="960" y="494" class="s">SOT89 · QBOOST</text>')
s = s.replace('<path d="M1084 310 H1116 M1084 370 H1116" stroke="#203348" stroke-width="3"/>', '')
s = s.replace('<text x="1060" y="400" class="s">C58/C59</text><text x="1080" y="424" class="s">47nF</text>', '<text x="1130" y="340" class="s">C58/C59</text><text x="1130" y="364" class="s">47nF</text>')
if 'M670 345 Q680' not in s:
    s = s.replace('<circle class="j" cx="340" cy="135"', '<path d="M670 345 Q680 326 690 345" stroke="white" stroke-width="7" fill="none"/><path d="M670 345 Q680 326 690 345" class="w"/><circle class="j" cx="340" cy="135"')
if 'M670 345 H690' not in s:
    s = s.replace('<path d="M670 345 Q680', '<path d="M670 345 H690" stroke="white" stroke-width="7" fill="none"/><path class="w" d="M680 330 V360"/><path d="M670 345 Q680', 1)
p.write_text(s,encoding='utf-8')
print('Visual proposal source cleaned; no CAD writes.')
