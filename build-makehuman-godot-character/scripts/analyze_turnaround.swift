#!/usr/bin/env swift
import AppKit
import CoreImage
import Foundation
import Vision

guard CommandLine.arguments.count == 4 else {
    fputs("usage: analyze_turnaround.swift INPUT_IMAGE OUTPUT_JSON OUTPUT_MASK\n", stderr)
    exit(2)
}

let sourcePath = CommandLine.arguments[1]
let outputPath = CommandLine.arguments[2]
let maskPath = CommandLine.arguments[3]
let fileManager = FileManager.default
try fileManager.createDirectory(
    at: URL(fileURLWithPath: outputPath).deletingLastPathComponent(),
    withIntermediateDirectories: true
)
try fileManager.createDirectory(
    at: URL(fileURLWithPath: maskPath).deletingLastPathComponent(),
    withIntermediateDirectories: true
)
guard let image = NSImage(contentsOfFile: sourcePath) else {
    fatalError("Unable to load reference image: \(sourcePath)")
}
var imageRect = NSRect(origin: .zero, size: image.size)
guard let cgImage = image.cgImage(forProposedRect: &imageRect, context: nil, hints: nil) else {
    fatalError("Unable to create CGImage")
}

let bodyRequest = VNDetectHumanBodyPoseRequest()
let faceRequest = VNDetectFaceLandmarksRequest()
let segmentationRequest = VNGeneratePersonSegmentationRequest()
segmentationRequest.qualityLevel = .accurate
segmentationRequest.outputPixelFormat = kCVPixelFormatType_OneComponent8
let handler = VNImageRequestHandler(cgImage: cgImage, orientation: .up, options: [:])
try handler.perform([bodyRequest, faceRequest, segmentationRequest])

if let buffer = segmentationRequest.results?.first?.pixelBuffer {
    let context = CIContext()
    try context.writePNGRepresentation(
        of: CIImage(cvPixelBuffer: buffer),
        to: URL(fileURLWithPath: maskPath),
        format: .L8,
        colorSpace: CGColorSpaceCreateDeviceGray()
    )
} else {
    fatalError("Vision did not produce a person segmentation mask")
}

let names: [(String, VNHumanBodyPoseObservation.JointName)] = [
    ("nose", .nose), ("neck", .neck),
    ("right_shoulder", .rightShoulder), ("right_elbow", .rightElbow),
    ("right_wrist", .rightWrist), ("left_shoulder", .leftShoulder),
    ("left_elbow", .leftElbow), ("left_wrist", .leftWrist),
    ("root", .root), ("right_hip", .rightHip), ("right_knee", .rightKnee),
    ("right_ankle", .rightAnkle), ("left_hip", .leftHip),
    ("left_knee", .leftKnee), ("left_ankle", .leftAnkle)
]
var joints: [String: [String: Double]] = [:]
if let body = bodyRequest.results?.first {
    for (label, name) in names {
        if let point = try? body.recognizedPoint(name), point.confidence > 0.05 {
            joints[label] = [
                "x": Double(point.location.x), "y": Double(point.location.y),
                "pixel_x": Double(point.location.x) * Double(cgImage.width),
                "pixel_y_from_top": (1.0 - Double(point.location.y)) * Double(cgImage.height),
                "confidence": Double(point.confidence)
            ]
        }
    }
}

var faceInfo: [String: Any] = [:]
if let face = faceRequest.results?.first {
    let box = face.boundingBox
    faceInfo["bounding_box"] = ["x": Double(box.origin.x), "y": Double(box.origin.y),
                                 "width": Double(box.width), "height": Double(box.height)]
    if let landmarks = face.landmarks {
        func points(_ region: VNFaceLandmarkRegion2D?) -> [[String: Double]] {
            guard let region else { return [] }
            return region.normalizedPoints.map { ["x": Double($0.x), "y": Double($0.y)] }
        }
        faceInfo["face_contour"] = points(landmarks.faceContour)
        faceInfo["left_eye"] = points(landmarks.leftEye)
        faceInfo["right_eye"] = points(landmarks.rightEye)
        faceInfo["nose"] = points(landmarks.nose)
        faceInfo["outer_lips"] = points(landmarks.outerLips)
    }
}

let result: [String: Any] = ["source": sourcePath, "image_width": cgImage.width,
                             "image_height": cgImage.height, "body_joints": joints,
                             "face": faceInfo]
let data = try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys])
try data.write(to: URL(fileURLWithPath: outputPath))
print(outputPath)
