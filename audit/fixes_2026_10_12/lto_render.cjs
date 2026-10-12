const path = require('path');
const sharp = require('C:/Users/Alksndr/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
(async () => {
  await sharp(path.join(__dirname, 'lto_balancer_booster.svg'))
    .png().toFile(path.join(__dirname, 'lto_balancer_booster.png'));
})();
