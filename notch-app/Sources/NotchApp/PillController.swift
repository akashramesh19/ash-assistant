import AppKit
import Combine
import SwiftUI

/// Owns the pill windows: one on every notched screen, plus a floating pill on
/// the main display when that screen has no notch. Rebuilds on display changes.
final class PillController {
    let model: PillModel
    private(set) var panels: [PillPanel] = []
    private var cancellable: AnyCancellable?

    init(model: PillModel) {
        self.model = model
        // Clicks reach the pill only while a confirmation is open.
        cancellable = model.$state.receive(on: DispatchQueue.main).sink { [weak self] state in
            self?.panels.forEach { $0.ignoresMouseEvents = (state != .confirm) }
        }
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.rebuild() }
        rebuild()
    }

    func rebuild() {
        panels.forEach { $0.orderOut(nil) }
        panels = []
        let mainScreen = NSScreen.screens.first   // the screen with the menu bar
        for screen in NSScreen.screens {
            let geometry = PillGeometry(screen: screen)
            guard geometry.hasNotch || screen == mainScreen else { continue }
            let host = PillHostingView(rootView: PillView(model: model, geometry: geometry))
            host.hasNotch = geometry.hasNotch
            host.rootView = PillView(model: model, geometry: geometry) { [frames = host.frames] frame in
                frames.frame = frame
            }
            let panel = PillPanel(frame: geometry.panelFrame(on: screen), content: host)
            panel.ignoresMouseEvents = (model.state != .confirm)
            panel.orderFrontRegardless()
            panels.append(panel)
            log("pill on \(screen.localizedName): notch=\(geometry.hasNotch) notchWidth=\(geometry.notchWidth) notchHeight=\(geometry.baseHeight) screen=\(screen.frame) frame=\(panel.frame)")
        }
    }
}

func log(_ message: String) {
    FileHandle.standardError.write(Data("[notch] \(message)\n".utf8))
}
