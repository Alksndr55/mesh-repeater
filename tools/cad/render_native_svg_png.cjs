// Rasterize exact native SVG paths, without redrawing any CAD geometry.
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const root = path.resolve(__dirname, '../..');
const input = path.resolve(process.argv[2]);
if (path.relative(root,input).startsWith('..')) throw Error('Input must stay in v2');
const sharpPath = process.argv[3] || 'C:/Users/Alksndr/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp';
const sharp = require(sharpPath);
(async () => {
  for (const filename of fs.readdirSync(input).filter(p => p.endsWith('.svg'))) {
    const source = path.join(input,filename);
    await sharp(source,{density:300}).flatten({background:'#ffffff'}).resize({width:1800}).png().toFile(source.slice(0,-4)+'.png');
    process.stdout.write(filename+' -> PNG\n');
  }
  // Exterior assembly top after X180 equals the native mirrored B view
  // rotated in-plane180. Keep the exact native SVG geometry within one
  // explicit viewing transform, rather than recreating its text or copper.
  for (const filename of fs.readdirSync(input).filter(p => p.endsWith('_back.svg'))) {
    const source = path.join(input,filename);
    const native = fs.readFileSync(source,'utf8');
    const m = native.match(/viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"/);
    if (!m) throw Error('Native SVG has no supported viewBox: '+source);
    const cx = Number(m[1])+Number(m[3])/2, cy = Number(m[2])+Number(m[4])/2;
    const endOpen = native.indexOf('>',native.indexOf('<svg'))+1;
    const endClose = native.lastIndexOf('</svg>');
    const transformed = native.slice(0,endOpen)+`\n<g transform="rotate(180 ${cx} ${cy})">\n`+native.slice(endOpen,endClose)+'\n</g>\n</svg>\n';
    const dest = path.join(input,filename.replace('_back.svg','_assembly_top.svg'));
    fs.writeFileSync(dest,transformed,'utf8');
    await sharp(Buffer.from(transformed),{density:300}).flatten({background:'#ffffff'}).resize({width:1800}).png().toFile(dest.slice(0,-4)+'.png');
    process.stdout.write(path.basename(dest)+' -> PNG / exact X180 assembly view\n');
    if (filename==='MeshRepeater2_Logic_back.svg') {
      const operator=path.join(input,'MeshRepeater2_Logic_operator_top');
      fs.copyFileSync(dest,operator+'.svg');
      fs.copyFileSync(dest.slice(0,-4)+'.png',operator+'.png');
      fs.writeFileSync(operator+'_view.json',JSON.stringify({
        source_native_view: filename,
        native_source_sha256: crypto.createHash('sha256').update(fs.readFileSync(source)).digest('hex'),
        board_assembly_rotation: 'X 180 degrees; native F components face down',
        image_transform: 'KiCad native --mirror B view, followed by in-plane 180 degree rotation',
        svg_transform: `rotate(180 ${cx} ${cy})`,
        output: 'Exterior operator top in the assembled orientation; CAD geometry unchanged'
      },null,2),'utf8');
    }
  }
  // Refresh export sidecars after rasterization, avoiding a self-referential
  // manifest hash and avoiding hashes of previous PNG/assembly-top artifacts.
  for (const filename of fs.readdirSync(input).filter(p=>p.endsWith('_exports.json'))) {
    const file = path.join(input,filename), doc = JSON.parse(fs.readFileSync(file,'utf8'));
    const stem=filename.slice(0,-'_exports.json'.length);
    doc.artifacts=fs.readdirSync(input).filter(p=>p.startsWith(stem)&&p!==filename).sort().map(p=>{
      const full=path.join(input,p);
      return {path:path.relative(root,full),sha256:crypto.createHash('sha256').update(fs.readFileSync(full)).digest('hex')};
    });
    fs.writeFileSync(file,JSON.stringify(doc,null,2),'utf8');
  }
})().catch(e=>{process.stderr.write(String(e)+'\n');process.exit(1)});
