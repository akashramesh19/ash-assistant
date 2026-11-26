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
    /// The stage line currently in force. Idle leaves it up. A reply covers it,
    /// and the line comes back when that reply's linger ends.
    private var running: CrewLine?
    /// A finished notice that arrived while a confirmation was open. Shown once,
    /// after that turn's reply has lingered.
    private var unseenFinished: CrewLine?
    static let lingerAfterIdle: TimeInterval = 5     // a reply or a finished notice stays this long after Ash stops talking

    private struct CrewLine {
        var status: String
        var message: String
    }

    /// Show a state. A reply or a finished crew notice is not wiped the moment
    /// Ash goes idle: it lingers briefly so it can be read. A running crew line
    /// stays until the next crew event. `immediate` skips the linger.
    /// `status` is the crew event's status (`running`, `done`, `done-unreviewed`, `failed`).
    func apply(_ newState: AshState, text: String = "", confirmID: String = "", immediate: Bool = false, status: String = "") {
        DispatchQueue.main.async {
            self.applyNow(newState, line: text, confirmID: confirmID, immediate: immediate, status: status)
        }
    }

    private func applyNow(_ newState: AshState, line: String, confirmID: String, immediate: Bool, status: String) {
        if newState == .crew {
            holdCrew(status: status, message: line)
            return
        }

        dismiss?.cancel()
        dismiss = nil

        if newState == .idle && immediate {
            // confirm_closed uses this while the question is up. The stored
            // crew line waits for the reply. A disconnect in any other state
            // drops it, because the agent is gone.
            if state == .confirm {
                state = .idle
                text = ""
                self.confirmID = ""
                return
            }
            running = nil
            unseenFinished = nil
            state = .idle
            text = ""
            self.confirmID = ""
            return
        }

        if newState == .idle {
            if state == .reply {
                scheduleLinger { [weak self] in self?.restoreAfterMessage() }
                return
            }
            if state == .crew && running != nil && unseenFinished == nil {
                return
            }
            if state == .crew {
                scheduleLinger { [weak self] in self?.blank() }
                return
            }
            restoreAfterMessage()
            return
        }

        state = newState
        text = line
        self.confirmID = confirmID
    }

    /// A crew event during a confirmation is stored. The question, the id, and
    /// the buttons stay. Anywhere else, it is shown now.
    private func holdCrew(status: String, message: String) {
        let line = CrewLine(status: status, message: message)
        if state == .confirm {
            if Self.isRunning(status) {
                running = line
                unseenFinished = nil
            } else {
                running = nil
                unseenFinished = line
            }
            return
        }
        let idleAlreadyLanded = dismiss != nil
        dismiss?.cancel()
        dismiss = nil
        if Self.isRunning(status) {
            running = line
            unseenFinished = nil
            state = .crew
            text = message
            confirmID = ""
            return
        }
        running = nil
        unseenFinished = nil
        state = .crew
        text = message
        confirmID = ""
        // Idle already started a linger for the reply this notice just replaced.
        // Start that linger again, or the finished line would stay up.
        if idleAlreadyLanded {
            scheduleLinger { [weak self] in self?.blank() }
        }
    }

    /// After a reply's linger: put the running line back, or show a finished
    /// notice that was waiting out a confirmation. A finished notice is shown
    /// once, then lingers like a reply.
    private func restoreAfterMessage() {
        dismiss = nil
        if let finished = unseenFinished {
            unseenFinished = nil
            running = nil
            state = .crew
            text = finished.message
            confirmID = ""
            scheduleLinger { [weak self] in self?.blank() }
            return
        }
        if let running {
            state = .crew
            text = running.message
            confirmID = ""
            return
        }
        blank()
    }

    private func blank() {
        dismiss = nil
        state = .idle
        text = ""
        confirmID = ""
    }

    private func scheduleLinger(_ action: @escaping () -> Void) {
        let item = DispatchWorkItem(block: action)
        dismiss = item
        DispatchQueue.main.asyncAfter(deadline: .now() + Self.lingerAfterIdle, execute: item)
    }

    private static func isRunning(_ status: String) -> Bool { status == "running" }
}
