import AppKit
import Combine
import SwiftUI

/// Owns the pill windows: one on every notched screen, plus a floating pill on
/// the main display when that screen has no notch. Rebuilds on display changes.
final class PillController {
    let model: PillModel
    private(set) var panels: [PillPanel] = []
    private var measuredPill: [ObjectIdentifier: CGSize] = [:]
    private var fittedPill: [ObjectIdentifier: CGSize] = [:]
    private var cancellable: AnyCancellable?

    init(model: PillModel) {
        self.model = model
        // Clicks reach the window only while a confirmation is open, and that
        // window is the pill itself. ignoresMouseEvents covers the whole window,
        // so a click beside the pill gets through only when the window is gone.
        cancellable = model.$state.receive(on: DispatchQueue.main).sink { [weak self] state in
            self?.applyFrames(for: state)
        }
        NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main
        ) { [weak self] _ in self?.rebuild() }
        rebuild()
    }

    func rebuild() {
        panels.forEach { $0.orderOut(nil) }
        panels = []
        measuredPill = [:]
        fittedPill = [:]
        let mainScreen = NSScreen.screens.first   // the screen with the menu bar
        for screen in NSScreen.screens {
            let geometry = PillGeometry(screen: screen)
            guard geometry.hasNotch || screen == mainScreen else { continue }
            let host = PillHostingView(rootView: PillView(model: model, geometry: geometry))
            host.hasNotch = geometry.hasNotch
            let initial = model.state == .confirm ? geometry.confirmFrame(on: screen) : geometry.panelFrame(on: screen)
            let panel = PillPanel(frame: initial, content: host)
            let frames = host.frames
            host.rootView = PillView(model: model, geometry: geometry) { [weak self, weak panel] pillFrame in
                frames.frame = pillFrame
                guard self?.model.state == .confirm else { return }
                // The preference arrives during layout. Resize on the next turn.
                DispatchQueue.main.async { [weak self, weak panel] in
                    self?.fitConfirmation(panel, to: pillFrame)
                }
            }
            panel.ignoresMouseEvents = (model.state != .confirm)
            panel.orderFrontRegardless()
            panels.append(panel)
            log("pill on \(screen.localizedName): notch=\(geometry.hasNotch) notchWidth=\(geometry.notchWidth) notchHeight=\(geometry.baseHeight) screen=\(screen.frame) frame=\(panel.frame)")
        }
    }

    /// Confirmation: mouse events on, window no wider than the pill.
    /// Anything else: the fixed frame, and mouse events off again.
    private func applyFrames(for state: AshState) {
        if state != .confirm {
            measuredPill = [:]
            fittedPill = [:]
        }
        for panel in panels {
            panel.ignoresMouseEvents = (state != .confirm)
            guard let screen = panel.screen else { continue }
            let geometry = PillGeometry(screen: screen)
            let frame: NSRect
            if state == .confirm, let size = measuredPill[ObjectIdentifier(panel)], size.width > 1, size.height > 1 {
                frame = geometry.frame(fitting: size, on: screen)
            } else if state == .confirm {
                frame = geometry.confirmFrame(on: screen)
            } else {
                frame = geometry.panelFrame(on: screen)
            }
            if !Self.nearlyEqual(panel.frame, frame) {
                panel.setFrame(frame, display: true)
            }
        }
    }

    /// Shrink the confirmation window to the pill that was just measured.
    /// Keeps the top edge of the fixed frame. A later, identical measurement
    /// does not set the frame again.
    private func fitConfirmation(_ panel: PillPanel?, to pillFrame: CGRect) {
        guard model.state == .confirm, let panel, pillFrame.width > 1, pillFrame.height > 1 else { return }
        let size = CGSize(width: pillFrame.width, height: pillFrame.height)
        let id = ObjectIdentifier(panel)
        measuredPill[id] = size
        if let previous = fittedPill[id], abs(previous.width - size.width) < 1, abs(previous.height - size.height) < 1 {
            return
        }
        guard let screen = panel.screen else { return }
        let fitted = PillGeometry(screen: screen).frame(fitting: size, on: screen)
        guard !Self.nearlyEqual(panel.frame, fitted) else {
            fittedPill[id] = size
            return
        }
        fittedPill[id] = size
        panel.setFrame(fitted, display: true)
    }

    private static func nearlyEqual(_ a: NSRect, _ b: NSRect) -> Bool {
        abs(a.origin.x - b.origin.x) < 0.5
            && abs(a.origin.y - b.origin.y) < 0.5
            && abs(a.size.width - b.size.width) < 0.5
            && abs(a.size.height - b.size.height) < 0.5
    }
}

func log(_ message: String) {
    FileHandle.standardError.write(Data("[notch] \(message)\n".utf8))
}
