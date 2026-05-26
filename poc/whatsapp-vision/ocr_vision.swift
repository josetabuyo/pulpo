#!/usr/bin/env swift
// macOS Vision OCR — usage: swift ocr_vision.swift <image_path>
import Vision
import AppKit
import Foundation

guard CommandLine.arguments.count > 1 else {
    print("Usage: swift ocr_vision.swift <image_path>")
    exit(1)
}

let imagePath = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    fputs("ERROR: Cannot load image: \(imagePath)\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true
request.recognitionLanguages = ["es", "en"]

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("ERROR: Vision request failed: \(error)\n", stderr)
    exit(1)
}

guard let observations = request.results else {
    print("[]")
    exit(0)
}

var results: [[String: Any]] = []
for obs in observations {
    guard let candidate = obs.topCandidates(1).first else { continue }
    let box = obs.boundingBox  // normalized coords (0-1), origin bottom-left
    results.append([
        "text": candidate.string,
        "confidence": candidate.confidence,
        "x": box.origin.x,
        "y": 1.0 - box.origin.y - box.size.height,  // flip to top-left origin
        "w": box.size.width,
        "h": box.size.height
    ])
}

let json = try! JSONSerialization.data(withJSONObject: results, options: [.prettyPrinted])
print(String(data: json, encoding: .utf8)!)
