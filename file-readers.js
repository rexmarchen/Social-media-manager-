/**
 * file-readers.js
 * ---------------
 * Extracts plain text from the file types this pipeline supports.
 * Add more extensions here (e.g. .pptx, .csv) if you need them later.
 */

const fs = require("fs");
const path = require("path");

const SUPPORTED_EXTENSIONS = [".txt", ".md", ".pdf", ".docx"];

function isSupported(filePath) {
  return SUPPORTED_EXTENSIONS.includes(path.extname(filePath).toLowerCase());
}

async function extractText(filePath) {
  const ext = path.extname(filePath).toLowerCase();

  if (ext === ".txt" || ext === ".md") {
    return fs.readFileSync(filePath, "utf8");
  }

  if (ext === ".pdf") {
    const pdfParse = require("pdf-parse");
    const buffer = fs.readFileSync(filePath);
    const data = await pdfParse(buffer);
    return data.text;
  }

  if (ext === ".docx") {
    const mammoth = require("mammoth");
    const buffer = fs.readFileSync(filePath);
    const result = await mammoth.extractRawText({ buffer });
    return result.value;
  }

  throw new Error(`Unsupported file type: ${ext}`);
}

module.exports = { isSupported, extractText, SUPPORTED_EXTENSIONS };
