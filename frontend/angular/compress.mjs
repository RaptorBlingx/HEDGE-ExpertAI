import { copyFileSync, mkdirSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const root = 'dist/expertai/browser';
mkdirSync(join(root, 'licenses'), { recursive: true });
copyFileSync('dist/expertai/3rdpartylicenses.txt', join(root, 'licenses/dependencies.txt'));
for (const file of readdirSync(root)) {
  if (/\.(js|css|html)$/.test(file)) {
    writeFileSync(join(root, file + '.gz'), gzipSync(readFileSync(join(root, file)), { level: 9 }));
  }
}
