import Foundation
import Vision
import CoreImage
import ImageIO

guard CommandLine.arguments.count == 3 else {
    fputs("Usage: person_union_mask.swift INPUT_IMAGE OUTPUT_MASK\n", stderr)
    exit(2)
}

let inputURL = URL(fileURLWithPath: CommandLine.arguments[1])
let outputURL = URL(fileURLWithPath: CommandLine.arguments[2])
try FileManager.default.createDirectory(
    at: outputURL.deletingLastPathComponent(),
    withIntermediateDirectories: true
)

guard
    let source = CGImageSourceCreateWithURL(inputURL as CFURL, nil),
    let image = CGImageSourceCreateImageAtIndex(source, 0, nil)
else {
    fputs("Could not decode input image\n", stderr)
    exit(1)
}

let handler = VNImageRequestHandler(cgImage: image, orientation: .up, options: [:])
let request = VNGeneratePersonInstanceMaskRequest()
try handler.perform([request])

guard let observation = request.results?.first else {
    fputs("No people detected\n", stderr)
    exit(1)
}

let instances = observation.allInstances
let buffer = try observation.generateScaledMaskForImage(
    forInstances: instances,
    from: handler
)
let mask = CIImage(cvPixelBuffer: buffer)
let context = CIContext()
try context.writePNGRepresentation(
    of: mask,
    to: outputURL,
    format: .L8,
    colorSpace: CGColorSpaceCreateDeviceGray()
)

print("Detected person instances: \(instances.sorted())")
print(outputURL.path)
