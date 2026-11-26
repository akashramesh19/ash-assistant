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

    /// The panel's frame: a fixed transparent area at the top centre of the
    /// screen. The pill is drawn inside it, so resizing never moves a window.
    func panelFrame(on screen: NSScreen) -> NSRect {
        let size = Self.panelSize
        let x = screen.frame.midX - size.width / 2
        let top = hasNotch ? screen.frame.maxY : screen.visibleFrame.maxY - 6
        return NSRect(x: x, y: top - size.height, width: size.width, height: size.height)
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
