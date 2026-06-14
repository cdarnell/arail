// arail-ocr — on-device image-text OCR via Apple Vision (VNRecognizeTextRequest).
//
// Compiled UNSIGNED with the stock toolchain (`xcrun swiftc -O ocr_helper.swift
// -o lab/bin/arail-ocr`). VNRecognizeTextRequest runs on a STATIC image and
// touches no privacy-gated resource (no camera, no mic) → no TCC grant, no
// code-signing, no Info.plist required. On-device, airgapped, zero deps.
//
// Usage:  arail-ocr --image <path>
//   stdout, exit 0:  {"ok": true, "text": "<lines joined by \n>"}
//   on failure, non-zero exit, stdout JSON:
//       {"ok": false, "error": "<code>", "message": "<actionable>"}
//     codes: "decode_failed" | "no_text" | "unsupported_image"

import Foundation
import AppKit
import Vision

func emit(_ obj: [String: Any], exit code: Int32) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: []),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    }
    exit(code)
}

func fail(_ error: String, _ message: String, _ code: Int32) -> Never {
    emit(["ok": false, "error": error, "message": message], exit: code)
}

// ── Parse args ──────────────────────────────────────────────────────────
var imagePath: String? = nil
let args = CommandLine.arguments
var i = 1
while i < args.count {
    if args[i] == "--image", i + 1 < args.count {
        imagePath = args[i + 1]
        i += 2
    } else {
        i += 1
    }
}

guard let path = imagePath else {
    fail("unsupported_image", "no --image argument", 2)
}

// ── Decode the image natively (PNG/JPEG/TIFF/BMP/GIF via NSImage). ───────
guard let nsImage = NSImage(contentsOfFile: path),
      let tiff = nsImage.tiffRepresentation,
      let bitmap = NSBitmapImageRep(data: tiff),
      let cgImage = bitmap.cgImage else {
    fail("decode_failed", "Couldn't read that image. Try a clearer PNG/JPEG.", 3)
}

// ── Run Vision text recognition (accurate, no language correction). ─────
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = false   // faithful to digits/identifiers/units

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fail("decode_failed", "OCR failed to run on that image.", 3)
}

let observations = request.results ?? []
var lines: [String] = []
for obs in observations {
    if let top = obs.topCandidates(1).first {
        lines.append(top.string)
    }
}

let text = lines.joined(separator: "\n")
if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
    fail("no_text", "No text found in that image.", 4)
}

emit(["ok": true, "text": text], exit: 0)
