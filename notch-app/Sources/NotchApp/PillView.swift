import SwiftUI

struct PillFrameKey: PreferenceKey {
    static var defaultValue: CGRect = .zero
    static func reduce(value: inout CGRect, nextValue: () -> CGRect) { value = nextValue() }
}

struct PillView: View {
    @ObservedObject var model: PillModel
    let geometry: PillGeometry
    var onPillFrame: (CGRect) -> Void = { _ in }

    var body: some View {
        let size = geometry.pillSize(for: model.state)
        ZStack(alignment: .top) {
            Color.clear
            VStack(spacing: 0) {
                topRow(width: size.width)
                    .frame(width: size.width, height: geometry.baseHeight)
                if model.state == .reply || model.state == .crew {
                    Text(model.text)
                        .font(.system(size: 13))
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.leading)
                        .lineLimit(4)
                        .padding(.horizontal, 16)
                        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
                }
                if model.state == .confirm {
                    confirmBody
                }
            }
            .frame(width: size.width, height: model.state == .confirm ? nil : size.height, alignment: .top)
            .fixedSize(horizontal: false, vertical: model.state == .confirm)
            .background(PillShape(hasNotch: geometry.hasNotch).fill(Color.black))
            .background(
                GeometryReader { proxy in
                    Color.clear.preference(key: PillFrameKey.self, value: proxy.frame(in: .named("panel")))
                }
            )
            .animation(.spring(response: 0.35, dampingFraction: 0.8), value: model.state)
        }
        .coordinateSpace(name: "panel")
        // While confirming, the root is the pill's width and sits at the top
        // of whatever height the window currently has. The controller then
        // shrinks the window to the measured pill, so the two match.
        .frame(
            width: model.state == .confirm ? size.width : PillGeometry.panelSize.width,
            height: model.state == .confirm ? nil : PillGeometry.panelSize.height,
            alignment: .top
        )
        .onPreferenceChange(PillFrameKey.self, perform: onPillFrame)
    }

    /// The row level with the notch: indicators sit left and right of it.
    @ViewBuilder
    private func topRow(width: CGFloat) -> some View {
        HStack(spacing: 0) {
            indicator(mirrored: false)
                .frame(maxWidth: .infinity)
            if geometry.hasNotch {
                Spacer().frame(width: geometry.notchWidth)
            }
            indicator(mirrored: true)
                .frame(maxWidth: .infinity)
        }
        .padding(.horizontal, 8)
    }

    @ViewBuilder
    private func indicator(mirrored: Bool) -> some View {
        switch model.state {
        case .listening:
            Bars(speed: 6, color: .green)
        case .speaking:
            Bars(speed: 3, color: .white)
        case .thinking:
            Dots()
        case .reply, .crew, .confirm:
            if mirrored { Circle().fill(model.state == .confirm ? Color.orange : Color.white.opacity(0.5)).frame(width: 6, height: 6) }
        case .idle:
            EmptyView()
        }
    }

    private var confirmBody: some View {
        VStack(spacing: 10) {
            Text(model.text)
                .font(.system(size: 13, weight: .medium))
                .foregroundStyle(.white)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 16)
            HStack(spacing: 12) {
                Button("No") { model.onAnswer(model.confirmID, "no") }
                    .buttonStyle(PillButtonStyle(fill: Color.white.opacity(0.18)))
                Button("Yes") { model.onAnswer(model.confirmID, "yes") }
                    .buttonStyle(PillButtonStyle(fill: Color.green.opacity(0.85)))
            }
        }
        .padding(.top, 6)
        .padding(.bottom, 12)
        .frame(maxWidth: .infinity, alignment: .top)
    }
}

/// Flat top (flush with the screen edge), rounded bottom corners.
struct PillShape: Shape {
    let hasNotch: Bool
    func path(in rect: CGRect) -> Path {
        let radius: CGFloat = hasNotch ? 16 : 12
        let shape = UnevenRoundedRectangle(
            topLeadingRadius: hasNotch ? 0 : radius, bottomLeadingRadius: radius,
            bottomTrailingRadius: radius, topTrailingRadius: hasNotch ? 0 : radius
        )
        return shape.path(in: rect)
    }
}

struct PillButtonStyle: ButtonStyle {
    let fill: Color
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.system(size: 13, weight: .semibold))
            .foregroundStyle(.white)
            .frame(width: 84, height: 28)
            .background(RoundedRectangle(cornerRadius: 9).fill(fill))
            .opacity(configuration.isPressed ? 0.6 : 1)
    }
}

struct Bars: View {
    let speed: Double
    let color: Color
    var body: some View {
        TimelineView(.animation) { context in
            let t = context.date.timeIntervalSinceReferenceDate * speed
            HStack(spacing: 3) {
                ForEach(0..<5, id: \.self) { i in
                    Capsule().fill(color)
                        .frame(width: 3, height: 6 + 10 * abs(sin(t + Double(i) * 0.8)))
                }
            }
        }
    }
}

struct Dots: View {
    var body: some View {
        TimelineView(.animation) { context in
            let t = context.date.timeIntervalSinceReferenceDate * 4
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { i in
                    Circle().fill(Color.white).frame(width: 5, height: 5)
                        .opacity(0.35 + 0.65 * abs(sin(t - Double(i) * 0.7)))
                }
            }
        }
    }
}
