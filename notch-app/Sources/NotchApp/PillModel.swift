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
    /// A finished notice not yet shown. Shown once, after the reply has lingered,
    /// or straight away when the pill is on a stage line or blank between turns.
    private var unseenFinished: CrewLine?
    /// Set when a confirmation closes, cleared when the reply is applied or a
    /// normal idle runs. Until then the turn is still inside respond(), and a
    /// crew event is stored rather than painted.
    private var awaitingReply = false
    /// Set when listening, thinking, speaking, or a reply is applied. Cleared
    /// on a normal idle. Stays set after a stage line is painted, so a finish
    /// that arrives before the acknowledgement is stored instead of shown.
    private var turnOpen = false
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
                awaitingReply = true
                return
            }
            awaitingReply = false
            turnOpen = false
            running = nil
            unseenFinished = nil
            state = .idle
            text = ""
            self.confirmID = ""
            return
        }

        if newState == .idle {
            awaitingReply = false
            turnOpen = false
            if state == .reply {
                scheduleLinger { [weak self] in self?.restoreAfterMessage() }
                return
            }
            if state == .crew && running != nil && unseenFinished == nil {
                return
            }
            if state == .crew && unseenFinished != nil {
                restoreAfterMessage()
                return
            }
            if state == .crew {
                scheduleLinger { [weak self] in self?.blank() }
                return
            }
            restoreAfterMessage()
            return
        }

        if newState == .reply {
            awaitingReply = false
        }
        if newState == .listening || newState == .thinking || newState == .speaking || newState == .reply {
            turnOpen = true
        }
        state = newState
        text = line
        self.confirmID = confirmID
    }

    /// A crew event during a confirmation, or before that turn's reply, is
    /// stored. A finished sentence during the turn is stored too. A finished
    /// sentence that lands on a stage line, or on a blank pill, is shown and
    /// lingers.
    private func holdCrew(status: String, message: String) {
        let line = CrewLine(status: status, message: message)
        if Self.isRunning(status) {
            // A finished sentence not yet shown stays queued. The new stage
            // comes back when that sentence's linger ends.
            running = line
            if unseenFinished != nil || state == .confirm || state == .reply || awaitingReply {
                return
            }
            dismiss?.cancel()
            dismiss = nil
            state = .crew
            text = message
            confirmID = ""
            return
        }
        if holdsFinished() {
            running = nil
            unseenFinished = line
            return
        }
        dismiss?.cancel()
        dismiss = nil
        running = nil
        unseenFinished = nil
        state = .crew
        text = message
        confirmID = ""
        scheduleLinger { [weak self] in self?.blank() }
    }

    /// Listening, thinking, speaking, and the reply stay on screen. So does an
    /// open question, and the gap after it closes until the reply or a normal idle.
    private func holdsFinished() -> Bool {
        if state == .confirm || awaitingReply || turnOpen { return true }
        switch state {
        case .listening, .thinking, .speaking, .reply:
            return true
        default:
            return false
        }
    }

    /// After a reply's linger: show a stored finished sentence once, then the
    /// running line if a newer stage is already waiting. Otherwise put the
    /// running line back.
    private func restoreAfterMessage() {
        dismiss = nil
        if let finished = unseenFinished {
            unseenFinished = nil
            state = .crew
            text = finished.message
            confirmID = ""
            scheduleLinger { [weak self] in self?.afterFinishedLinger() }
            return
        }
        showRunningOrBlank()
    }

    private func afterFinishedLinger() {
        dismiss = nil
        showRunningOrBlank()
    }

    private func showRunningOrBlank() {
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
