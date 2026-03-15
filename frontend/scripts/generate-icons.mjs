import sharp from 'sharp'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const publicDir = resolve(__dirname, '../public')
const svg = readFileSync(resolve(publicDir, 'icon.svg'))

const sizes = [72, 96, 128, 144, 152, 192, 384, 512]

for (const size of sizes) {
  await sharp(svg)
    .resize(size, size)
    .png()
    .toFile(resolve(publicDir, `icon-${size}.png`))
  console.log(`Generated icon-${size}.png`)
}

// Apple touch icon (180x180)
await sharp(svg)
  .resize(180, 180)
  .png()
  .toFile(resolve(publicDir, 'apple-touch-icon.png'))
console.log('Generated apple-touch-icon.png')

// Favicon PNG fallback (32x32)
const faviconSvg = readFileSync(resolve(publicDir, 'favicon.svg'))
await sharp(faviconSvg)
  .resize(32, 32)
  .png()
  .toFile(resolve(publicDir, 'favicon.png'))
console.log('Generated favicon.png')

console.log('All icons generated.')
