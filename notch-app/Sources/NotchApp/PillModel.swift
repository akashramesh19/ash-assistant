import Foundation

enum AshState: String {
    case idle, listening, thinking, speaking, reply, confirm, crew
}

/// What the pill is showing. One model is shared by every pill window, so the
/// notch and the floating pill always agree.
final class PillModel: ObservableObject {
    @Published var state: AshState = .idle
    @Published var text: String = ""          // reply text, confirmation question, or crew message
    @Published var confirmID: String = ""

    /// Called when the user clicks Yes or No (id, "yes" | "no").
    var onAnswer: (String, String) -> Void = { _, _ in }

    private var dismiss: DispatchWorkItem?
    static let lingerAfterIdle: TimeInterval = 5     // a reply stays this long after Ash stops talking
    static let longestReply: TimeInterval = 25       // safety net if "idle" never arrives

    /// Show a state. A reply or crew notice is not wiped the moment Ash goes
    /// idle: it lingers briefly so it can be read. `immediate` skips that.
    func apply(_ newState: AshState, text: String = "", confirmID: String = "", immediate: Bool = false) {
        DispatchQueue.main.async {
            self.dismiss?.cancel()
            let showingMessage = self.state == .reply || self.state == .crew
            if newState == .idle && showingMessage && !immediate {
                self.schedule(after: Self.lingerAfterIdle)
                return
            }
            self.state = newState
            self.text = text
            self.confirmID = confirmID
            if newState == .reply || newState == .crew {
                self.schedule(after: Self.longestReply)
            }
        }
    }

    private func schedule(after seconds: TimeInterval) {
        let item = DispatchWorkItem { [weak self] in
            self?.state = .idle
            self?.text = ""
        }
        dismiss = item
        DispatchQueue.main.asyncAfter(deadline: .now() + seconds, execute: item)
    }
}
