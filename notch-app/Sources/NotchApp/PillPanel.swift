import AppKit
import SwiftUI

/// A borderless, non-activating panel above the menu bar, on every Space and
/// over full-screen apps. It can become key so a confirmation button receives
/// the click, and it never becomes the main window.
final class PillPanel: NSPanel {
    init(frame: NSRect, content: NSView) {
        super.init(
            contentRect: frame,
            styleMask: [.borderless, .nonactivatingPanel],
            backing: .buffered,
            defer: false
        )
        isOpaque = false
        backgroundColor = .clear
        hasShadow = false
        isFloatingPanel = true
        hidesOnDeactivate = false
        level = NSWindow.Level(rawValue: NSWindow.Level.mainMenu.rawValue + 3)
        collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        ignoresMouseEvents = true   // the whole window lets clicks through until a confirmation opens
        contentView = content
    }

    // A SwiftUI button receives the click only when the panel can become key.
    // It still cannot become main, and the style mask keeps it non-activating.
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }

    /// AppKit normally pushes windows out of the menu bar area; the pill must sit in it.
    override func constrainFrameRect(_ frameRect: NSRect, to screen: NSScreen?) -> NSRect { frameRect }
}

/// Shared with the SwiftUI tree, which reports the pill's frame in panel coordinates.
final class PillFrameBox {
    var frame = CGRect.zero
}

/// Claims a click only when it lands on the pill shape. Returning nil does
/// not pass the click through: AppKit has already delivered it to this panel.
/// A confirmation avoids that by shrinking the window to the pill. Every
/// other state ignores mouse events, which is what lets the menu bar have them.
final class PillHostingView: NSHostingView<PillView> {
    let frames = PillFrameBox()
    var hasNotch = false

    override func hitTest(_ point: NSPoint) -> NSView? {
        let rect = pillRectInView()
        guard rect.width > 1, rect.height > 1, pillContains(point, in: rect) else { return nil }
        return super.hitTest(point) ?? self
    }

    private func pillRectInView() -> CGRect {
        var rect = frames.frame
        if !isFlipped {
            rect.origin.y = bounds.height - rect.origin.y - rect.height
        }
        return rect
    }

    /// Local point is y-down, matching PillShape.
    private func pillContains(_ point: NSPoint, in rect: CGRect) -> Bool {
        let local = CGPoint(
            x: point.x - rect.minX,
            y: isFlipped ? point.y - rect.minY : rect.maxY - point.y
        )
        return PillShape(hasNotch: hasNotch).path(in: CGRect(origin: .zero, size: rect.size)).contains(local)
    }
}
