// arail-stt — on-device Apple Speech file transcription helper.
//
// Usage: arail-stt --audio <path> --locale en-US [--timeout 120]
//   stdout (exit 0): {"ok":true,"transcript":"...","segments":[{"text":"...","ts":0.0}],
//                     "confidence":0.0,"on_device":true}
//   on failure: exit non-zero, stderr: {"ok":false,"error":"<code>","message":"..."}
//   error codes: permission_denied | no_speech | model_unavailable |
//                decode_failed | timeout | unsupported_audio
//
// On-device ONLY: requiresOnDeviceRecognition = true → never contacts Apple
// servers → works airgapped. This is the ONLY file allowed to import Speech /
// AVFoundation (WC-B seam).

import Foundation
import Speech
import AVFoundation

func emitError(_ code: String, _ message: String) -> Never {
    let obj: [String: Any] = ["ok": false, "error": code, "message": message]
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let s = String(data: data, encoding: .utf8) {
        FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
    }
    exit(2)
}

func arg(_ name: String) -> String? {
    let a = CommandLine.arguments
    if let i = a.firstIndex(of: name), i + 1 < a.count { return a[i + 1] }
    return nil
}

let audioPath = arg("--audio") ?? ""
let locale = arg("--locale") ?? "en-US"
let timeout = Double(arg("--timeout") ?? "120") ?? 120.0

if audioPath.isEmpty { emitError("decode_failed", "no --audio path given") }
let url = URL(fileURLWithPath: audioPath)
if !FileManager.default.fileExists(atPath: audioPath) {
    emitError("decode_failed", "audio file not found: \(audioPath)")
}

let sema = DispatchSemaphore(value: 0)

SFSpeechRecognizer.requestAuthorization { status in
    if status != .authorized {
        emitError("permission_denied",
                  "Speech recognition permission was denied. Enable it in System Settings → Privacy & Security → Speech Recognition.")
    }
    sema.signal()
}
_ = sema.wait(timeout: .now() + 30)

guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: locale)) else {
    emitError("model_unavailable", "No speech recognizer for locale \(locale).")
}
if !recognizer.supportsOnDeviceRecognition {
    emitError("model_unavailable", "On-device speech model unavailable for \(locale).")
}

let request = SFSpeechURLRecognitionRequest(url: url)
request.requiresOnDeviceRecognition = true
request.shouldReportPartialResults = false

let done = DispatchSemaphore(value: 0)
var finished = false

recognizer.recognitionTask(with: request) { result, error in
    if finished { return }
    if let error = error {
        finished = true
        emitError("decode_failed", "Transcription failed: \(error.localizedDescription)")
    }
    guard let result = result, result.isFinal else { return }
    finished = true

    let best = result.bestTranscription
    let text = best.formattedString
    if text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
        emitError("no_speech", "Nothing was heard in the recording.")
    }
    var segments: [[String: Any]] = []
    var confSum: Float = 0
    var confN: Int = 0
    for seg in best.segments {
        segments.append(["text": seg.substring, "ts": seg.timestamp])
        confSum += seg.confidence
        confN += 1
    }
    let confidence = confN > 0 ? Double(confSum) / Double(confN) : 0.0
    let obj: [String: Any] = [
        "ok": true, "transcript": text, "segments": segments,
        "confidence": confidence, "on_device": true,
    ]
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    }
    done.signal()
}

if done.wait(timeout: .now() + timeout) == .timedOut {
    emitError("timeout", "Transcription timed out after \(Int(timeout))s.")
}
exit(0)
