// Minimal .env loader — no external deps
const fs   = require('fs');
const path = require('path');
const file = path.join(__dirname, '.env');
if (fs.existsSync(file)) {
  fs.readFileSync(file, 'utf8').split('\n').forEach(line => {
    const [k, ...v] = line.split('=');
    if (k && v.length && !k.startsWith('#')) {
      process.env[k.trim()] = v.join('=').trim();
    }
  });
}
