import AppKit
import SwiftUI

/// Debug: render each state of each pill kind to a PNG, without needing
/// screen-recording permission (the view renders itself, not the screen).
enum Snapshot {
    static func render(into directory: String) {
        MainActor.assumeIsolated {
            try? FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
            var done = Set<Bool>()
            for screen in NSScreen.screens {
                let geometry = PillGeometry(screen: screen)
                guard done.insert(geometry.hasNotch).inserted else { continue }
                for state in [AshState.idle, .listening, .thinking, .speaking, .reply, .confirm, .crew] {
                    let model = PillModel()
                    model.state = state
                    model.text = state == .confirm ? "Ash wants to move report.txt to Archive. Go ahead?" : "22 and clear, Sir. Wear the good jacket."
                    let view = PillView(model: model, geometry: geometry)
                        .background(Color(white: 0.55))
                    let renderer = ImageRenderer(content: view)
                    renderer.scale = 2
                    guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
                          let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else {
                        log("snapshot failed for \(state)")
                        continue
                    }
                    let name = "\(geometry.hasNotch ? "notch" : "float")-\(state.rawValue).png"
                    try? png.write(to: URL(fileURLWithPath: directory).appendingPathComponent(name))
                }
            }
            log("snapshots written to \(directory)")
        }
    }

    /// Debug: capture the real, live windows as they are right now.
    static func renderLive(_ panels: [PillPanel], into directory: String) {
        MainActor.assumeIsolated {
            try? FileManager.default.createDirectory(atPath: directory, withIntermediateDirectories: true)
            for (index, panel) in panels.enumerated() {
                guard let view = panel.contentView, let rep = view.bitmapImageRepForCachingDisplay(in: view.bounds) else { continue }
                view.cacheDisplay(in: view.bounds, to: rep)
                if let png = rep.representation(using: .png, properties: [:]) {
                    try? png.write(to: URL(fileURLWithPath: directory).appendingPathComponent("live-\(index).png"))
                }
            }
            log("live windows written to \(directory)")
        }
    }
}
