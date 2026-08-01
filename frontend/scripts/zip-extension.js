import fs from 'fs'
import path from 'path'
import AdmZip from 'adm-zip'

const EXT_DIR = path.resolve(import.meta.dirname, '../../extension')
const OUT_DIR = path.resolve(import.meta.dirname, '../public')
const OUT_FILE = path.join(OUT_DIR, 'context-compressor-extension.zip')

if (!fs.existsSync(EXT_DIR)) {
  console.warn('⚠️  ../extension not found. Skipping zip.')
  process.exit(0)
}

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true })
}

const zip = new AdmZip()
zip.addLocalFolder(EXT_DIR, 'context-compressor-extension')
zip.writeZip(OUT_FILE)
console.log('✅ Extension zipped to', OUT_FILE)
