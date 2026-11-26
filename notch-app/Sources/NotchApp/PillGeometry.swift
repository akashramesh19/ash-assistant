import AppKit

/// Where and how big the pill is on one screen.
struct PillGeometry {
    let hasNotch: Bool
    let notchWidth: CGFloat
    let baseHeight: CGFloat   // height of the top row: the notch height, or a floating pill's height

    static let panelSize = CGSize(width: 480, height: 200)

    init(screen: NSScreen) {
        let inset = screen.safeAreaInsets.top
        if inset > 0, let left = screen.auxiliaryTopLeftArea, let right = screen.auxiliaryTopRightArea {
            hasNotch = true
            notchWidth = screen.frame.width - left.width - right.width
            baseHeight = inset
        } else {
            hasNotch = false
            notchWidth = 0
            baseHeight = 28
        }
    }

    /// The panel's frame at every state except confirmation: a fixed
    /// transparent area at the top centre. The pill is drawn inside it.
    /// Mouse events are ignored, so the clear part does not take clicks.
    func panelFrame(on screen: NSScreen) -> NSRect {
        let size = Self.panelSize
        let x = screen.frame.midX - size.width / 2
        let top = hasNotch ? screen.frame.maxY : screen.visibleFrame.maxY - 6
        return NSRect(x: x, y: top - size.height, width: size.width, height: size.height)
    }

    /// Provisional window while a confirmation is opening. Same top edge and
    /// height as panelFrame, only as wide as the confirm pill, so the question
    /// can lay out. The controller then shrinks the height to the measured pill.
    func confirmFrame(on screen: NSScreen) -> NSRect {
        let full = panelFrame(on: screen)
        let width = pillSize(for: .confirm).width
        return NSRect(x: full.midX - width / 2, y: full.minY, width: width, height: full.height)
    }

    /// A window the size of the pill, top edge kept where panelFrame has it,
    /// so the clear strip beside and below the pill is not part of the window.
    func frame(fitting pill: CGSize, on screen: NSScreen) -> NSRect {
        let full = panelFrame(on: screen)
        return NSRect(
            x: full.midX - pill.width / 2,
            y: full.maxY - pill.height,
            width: pill.width,
            height: pill.height
        )
    }

    /// Size of the visible pill for a state.
    func pillSize(for state: AshState) -> CGSize {
        let flank: CGFloat = 54
        switch state {
        case .idle:
            return hasNotch ? CGSize(width: notchWidth, height: baseHeight) : CGSize(width: 46, height: 16)
        case .listening, .thinking, .speaking:
            let width = hasNotch ? notchWidth + flank * 2 : 150
            return CGSize(width: width, height: baseHeight)
        case .reply, .crew:
            return CGSize(width: max(hasNotch ? notchWidth + 220 : 360, 360), height: baseHeight + 84)
        case .confirm:
            return CGSize(width: max(hasNotch ? notchWidth + 220 : 380, 380), height: baseHeight + 128)
        }
    }
}
