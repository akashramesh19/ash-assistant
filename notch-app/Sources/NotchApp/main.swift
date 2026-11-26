import AppKit

// docs/notch-design.md steps 1-2: the pill window, driven by the Python agent
// over the socket (pc-agent/ui_bridge.py), or by typed commands for debugging.
//
//   swift run NotchApp
//   then type:  idle | listening | thinking | speaking | reply <text>
//               | confirm <question> | crew <message> | click yes|no | snapshot [dir] | live [dir] | quit
//
// A Yes/No click prints "answer <id> yes|no" to stdout. Later steps replace the
// typed commands with the socket to the Python agent.

let app = NSApplication.shared
app.setActivationPolicy(.accessory)   // no Dock icon, no app switcher entry

let model = PillModel()
let client = BridgeClient(path: BridgeClient.defaultPath(), model: model)
model.onAnswer = { id, answer in
    print("answer \(id) \(answer)")
    client.sendAnswer(id: id, answer: answer)
}
let controller = PillController(model: model)
client.start()

func handle(_ line: String) {
    log("command: \(line)")
    let parts = line.split(separator: " ", maxSplits: 1).map(String.init)
    guard let command = parts.first?.lowercased() else { return }
    let rest = parts.count > 1 ? parts[1] : ""
    switch command {
    case "idle", "listening", "thinking", "speaking":
        model.apply(AshState(rawValue: command)!, immediate: true)
    case "reply":
        model.apply(.reply, text: rest.isEmpty ? "22 and clear, Sir. Wear the good jacket." : rest)
    case "crew":
        model.apply(.crew, text: rest.isEmpty ? "Your draft is ready, Sir." : rest)
    case "confirm":
        model.apply(.confirm, text: rest.isEmpty ? "Move report.txt into Archive?" : rest, confirmID: "debug")
    case "snapshot":
        DispatchQueue.main.async { Snapshot.render(into: rest.isEmpty ? "snapshots" : rest) }
    case "live":
        DispatchQueue.main.async { Snapshot.renderLive(controller.panels, into: rest.isEmpty ? "live" : rest) }
    case "click":   // debug: press the Yes/No button for the open confirmation
        DispatchQueue.main.async { model.onAnswer(model.confirmID, rest == "no" ? "no" : "yes") }
    case "quit":
        DispatchQueue.main.async { NSApp.terminate(nil) }
    default:
        log("unknown command: \(line)")
    }
}

Thread {
    while let line = readLine() { handle(line.trimmingCharacters(in: .whitespaces)) }
}.start()

app.run()
